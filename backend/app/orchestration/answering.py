from __future__ import annotations

import re
from collections import Counter

from app.config import OPENAI_API_KEY, OPENAI_CHAT_MODEL
from app.models.schemas import ExtractedFact, Source
from app.orchestration.query import QueryUnderstanding
from app.rag.keyword import tokens
from app.store import Dataset


def dataset_vocabulary(dataset: Dataset) -> list[str]:
    terms = []
    for segment in dataset.segments:
        terms.extend([segment.title, segment.source_name])
    for fact in dataset.facts:
        terms.extend([fact.subject, fact.object, fact.qualifier])
    return [term for term in dict.fromkeys(t.strip() for t in terms if t and len(t.strip()) > 2)]


def find_fact_match(dataset: Dataset, query: QueryUnderstanding) -> ExtractedFact | None:
    target_text = query.role_target or query.target or query.normalized
    target_terms = set(tokens(target_text))
    qualifier_terms = set(tokens(query.qualifier))
    query_terms = set(tokens(query.expanded))
    candidates: list[tuple[float, ExtractedFact]] = []
    for fact in dataset.facts:
        fact_terms = set(tokens(" ".join([fact.fact_type, fact.subject, fact.predicate, fact.object, fact.qualifier, fact.text])))
        if query.intent == "location" and fact.subject not in {"venue", "location", "address", "office"}:
            continue
        if query.intent == "time" and fact.subject not in {"date", "time"}:
            continue
        if query.intent == "point_lookup" and target_terms:
            subject_terms = set(tokens(fact.subject))
            if not (target_terms & subject_terms):
                continue
            if query.role_target and query.role_target != fact.subject:
                continue
            if qualifier_terms and not (qualifier_terms & fact_terms) and not _qualifier_acronym_matches(qualifier_terms, fact):
                continue
        score = len(query_terms & fact_terms) + 2 * len(target_terms & fact_terms) + fact.confidence
        if qualifier_terms:
            score += 2 * len(qualifier_terms & fact_terms)
        if query.intent in {"point_lookup", "location", "time"} and fact.fact_type in {"role", "contact", "event"}:
            score += 1.2
        if query.intent == "location" and fact.subject in {"venue", "location", "address"}:
            score += 3
        if query.intent == "time" and fact.subject in {"date", "time"}:
            score += 3
        if score >= 2.4:
            candidates.append((score, fact))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1] if candidates else None


def _qualifier_acronym_matches(qualifier_terms: set[str], fact: ExtractedFact) -> bool:
    text = " ".join([fact.qualifier, fact.object, fact.text])
    skip = {"and", "of", "the", "for", "in", "at", "to"}
    words = [word for word in re.findall(r"[A-Za-z]+", text) if len(word) > 2 and word.lower() not in skip]
    acronyms = set()
    for size in range(2, min(6, len(words)) + 1):
        for index in range(0, len(words) - size + 1):
            initials = "".join(word[0].lower() for word in words[index:index + size])
            acronyms.add(initials)
    return bool(qualifier_terms & acronyms)


def rerank_sources(query: QueryUnderstanding, sources: list[Source], fact_match: ExtractedFact | None = None, k: int = 8) -> list[Source]:
    q_terms = set(tokens(query.expanded))
    target_terms = set(tokens(query.target))
    reranked: list[Source] = []
    for source in sources:
        text = f"{source.title} {source.text}"
        s_terms = set(tokens(text))
        proximity_bonus = _proximity_bonus(query, source.text)
        score = source.score + len(q_terms & s_terms) * 1.2 + len(target_terms & s_terms) * 2.4 + proximity_bonus
        reason_bits = []
        if target_terms & s_terms:
            reason_bits.append(f"matched target terms: {', '.join(sorted(target_terms & s_terms)[:4])}")
        if q_terms & s_terms:
            reason_bits.append(f"matched query terms: {', '.join(sorted(q_terms & s_terms)[:5])}")
        if proximity_bonus:
            reason_bits.append("role/entity terms appear near each other")
        reranked.append(source.model_copy(update={"score": round(score, 4), "match_reason": "; ".join(reason_bits)}))

    if fact_match:
        fact_source = Source(
            id=fact_match.source_id,
            title=f"{fact_match.fact_type}: {fact_match.subject}",
            file_name=fact_match.source_name,
            text=fact_match.text or f"{fact_match.subject} {fact_match.predicate} {fact_match.object}",
            score=999,
            match_reason="matched extracted structured fact",
        )
        reranked.insert(0, fact_source)

    seen = set()
    unique = []
    for source in sorted(reranked, key=lambda item: item.score, reverse=True):
        key = (source.id, source.text[:120])
        if key in seen:
            continue
        seen.add(key)
        unique.append(source)
    return unique[:k]


def synthesize_answer(query: QueryUnderstanding, sources: list[Source], fact_match: ExtractedFact | None) -> tuple[str, str, float]:
    if fact_match:
        direct = _answer_from_fact(query, fact_match)
        return direct, direct, max(0.82, fact_match.confidence)

    if not sources:
        return "", "I could not find that in the uploaded data.", 0.0

    if query.intent in {"point_lookup", "location", "time"}:
        target = query.role_target or query.target or "that fact"
        closest = _clean_evidence_text(sources[0].text)
        answer = (
            f"I could not find a confirmed answer for {target!r} in the uploaded data. "
            f"The closest evidence I found says: {closest[:360]} [1]"
        )
        return "", answer, 0.28

    if OPENAI_API_KEY:
        try:
            context = "\n\n".join(f"[{idx+1}] {source.text}" for idx, source in enumerate(sources[:6]))
            from openai import OpenAI

            client = OpenAI(api_key=OPENAI_API_KEY)
            response = client.chat.completions.create(
                model=OPENAI_CHAT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Answer the user's question strictly from the provided context. "
                            "Start with a direct answer. Cite sources as [1], [2]. "
                            "If the answer is not in context, say you could not find it in the uploaded data."
                        ),
                    },
                    {"role": "user", "content": f"Question: {query.normalized}\nIntent: {query.intent}\n\nContext:\n{context}"},
                ],
                temperature=0.05,
            )
            answer = response.choices[0].message.content or ""
            return answer, answer, 0.78 if answer else 0.0
        except Exception:
            pass

    answer = _extractive_answer(query, sources)
    return answer, answer, 0.62 if answer else 0.0


def validate_answer(query: QueryUnderstanding, answer: str, sources: list[Source], fact_match: ExtractedFact | None, confidence: float) -> dict:
    evidence_text = " ".join(source.text for source in sources[:5]).lower()
    answer_lower = answer.lower()
    target_terms = set(tokens(query.target))
    status = "grounded"
    reasons = []

    if confidence >= 0.8 and answer:
        return {"status": "grounded", "reasons": ["A high-confidence structured or extracted result matched the query."]}
    if fact_match:
        reasons.append("A structured extracted fact matched the query.")
    if not answer or "could not find" in answer_lower:
        status = "not_found"
        reasons.append("No answerable evidence was found.")
    elif query.intent in {"point_lookup", "location", "time"} and not fact_match:
        if target_terms and not (target_terms & set(tokens(evidence_text + " " + answer_lower))):
            status = "weak_evidence"
            reasons.append("The top evidence did not contain the requested target terms.")
        if confidence < 0.55:
            status = "weak_evidence"
            reasons.append("Answer confidence is below threshold.")
    elif confidence < 0.45:
        status = "weak_evidence"
        reasons.append("Evidence score is low.")

    if status != "grounded" and query.intent in {"point_lookup", "location", "time"} and not fact_match:
        answer = "I could not find that in the uploaded data."

    return {"status": status, "reasons": reasons or ["Answer is supported by the retrieved evidence."]}


def _answer_from_fact(query: QueryUnderstanding, fact: ExtractedFact) -> str:
    if fact.fact_type == "role":
        return f"The {fact.subject} is {fact.object}." + (f" This is in the context of {fact.qualifier}." if fact.qualifier else "")
    if fact.fact_type == "contact":
        return f"The {fact.subject} is {fact.object}." + (f" This is listed under {fact.qualifier}." if fact.qualifier else "")
    if fact.fact_type == "event":
        return f"The {fact.subject} is {fact.object}." + (f" This is listed under {fact.qualifier}." if fact.qualifier else "")
    return f"{fact.subject} {fact.predicate} {fact.object}."


def _extractive_answer(query: QueryUnderstanding, sources: list[Source]) -> str:
    q_terms = set(tokens(query.expanded))
    sentences = []
    for idx, source in enumerate(sources[:6], start=1):
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", source.text):
            clean = _clean_evidence_text(sentence)
            if len(clean) < 25:
                continue
            overlap = len(q_terms & set(tokens(clean)))
            if overlap:
                sentences.append((overlap, idx, clean))
    sentences.sort(key=lambda item: item[0], reverse=True)
    if not sentences:
        closest = _clean_evidence_text(sources[0].text)
        return f"I found related evidence, but not a direct answer: {closest[:450]} [1]"
    if query.intent == "list":
        items = [f"- {sentence} [{idx}]" for _, idx, sentence in sentences[:6]]
        return "Here is what I found:\n" + "\n".join(items)
    return " ".join(f"{sentence} [{idx}]" for _, idx, sentence in sentences[:4])


def _clean_evidence_text(text: str) -> str:
    cleaned_lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("=== URL:"):
            continue
        if line.lower().startswith(("title:", "description:", "document links:")):
            continue
        cleaned_lines.append(line)
    cleaned = " ".join(cleaned_lines)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _proximity_bonus(query: QueryUnderstanding, text: str) -> float:
    lower = text.lower()
    target_terms = list(tokens(query.target))
    if not target_terms:
        return 0
    positions = [lower.find(term) for term in target_terms if lower.find(term) >= 0]
    if not positions:
        return 0
    role_terms = ["is", ":", "-", "held", "by", "serves", "as", "principal", "ceo", "venue", "speaker", "head"]
    for pos in positions:
        window = lower[max(0, pos - 120):pos + 180]
        if any(term in window for term in role_terms):
            return 4.0
    return 0
