from __future__ import annotations

import re
from uuid import uuid4

from app.models.schemas import ExtractedFact, Segment


ROLE_WORDS = (
    "principal", "ceo", "cto", "cfo", "founder", "chairman", "chairperson", "director",
    "manager", "head", "hod", "coordinator", "organizer", "speaker", "host", "venue",
    "president", "secretary", "dean", "administrator", "lead", "owner",
)
CONTACT_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\+?\d[\d\s().-]{7,}\d")
DATE_RE = re.compile(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Z][a-z]+\s+\d{4}|[A-Z][a-z]+\s+\d{1,2},?\s+\d{4})\b")
NAME_RE = re.compile(r"\b(?:Dr\.|Mr\.|Mrs\.|Ms\.|Prof\.)?\s*[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,4}\b")
FAKE_ROLE_OBJECT_WORDS = {
    "message", "about", "menu", "home", "login", "apply", "admission", "contact",
    "news", "event", "events", "downloads", "programs", "programmes", "departments",
    "library", "research", "careers", "examination", "autonomous", "certification",
}


def normalize_role(role: str) -> str:
    role = role.lower().strip()
    aliases = {
        "hod": "head of department",
        "head": "head",
        "chairperson": "chairman",
    }
    return aliases.get(role, role)


def _fact(segment: Segment, fact_type: str, subject: str, predicate: str, obj: str, qualifier: str, confidence: float, text: str) -> ExtractedFact:
    return ExtractedFact(
        id=str(uuid4()),
        fact_type=fact_type,
        subject=subject.strip(),
        predicate=predicate.strip(),
        object=obj.strip(),
        qualifier=qualifier.strip(),
        source_id=segment.id,
        source_name=segment.source_name,
        confidence=round(confidence, 2),
        text=text.strip()[:1200],
    )


def _looks_like_person_or_org(value: str) -> bool:
    clean = re.sub(r"\s+", " ", value.strip())
    if not clean or len(clean) > 80:
        return False
    words = [word.lower().strip(".,:;()[]") for word in clean.split()]
    if any(word in FAKE_ROLE_OBJECT_WORDS for word in words):
        return False
    if re.search(r"\b(?:Dr\.|Mr\.|Mrs\.|Ms\.|Prof\.|Fr\.)\s+[A-Z]", clean):
        return True
    if len(words) in {2, 3, 4} and all(re.match(r"^[A-Z][A-Za-z.'-]+$", part.strip(".,:;()[]")) for part in clean.split()):
        return True
    return False


def extract_facts_from_segments(segments: list[Segment]) -> list[ExtractedFact]:
    facts: list[ExtractedFact] = []
    for segment in segments:
        text = segment.text
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # Key-value records: Role: Principal, Name: Dr. X, Venue: Hall, Date: ...
        current: dict[str, str] = {}
        def flush_current() -> None:
            nonlocal current
            if not current:
                return
            name = current.get("name") or current.get("person") or current.get("speaker")
            role = current.get("role") or current.get("title") or current.get("designation")
            current_text = "\n".join(f"{k}: {v}" for k, v in current.items())
            if name and role:
                facts.append(_fact(segment, "role", normalize_role(role), "held_by", name, current.get("department", ""), 0.9, current_text))
            for key, value in current.items():
                key_norm = key.lower()
                if key_norm in {"email", "phone", "contact", "address"}:
                    facts.append(_fact(segment, "contact", key_norm, "value", value, name or role or segment.title, 0.86, current_text))
                if key_norm in {"venue", "location", "date", "time", "organizer"}:
                    facts.append(_fact(segment, "event", key_norm, "value", value, name or segment.title, 0.8, current_text))
            current = {}

        for line in lines + [""]:
            match = re.match(r"^([A-Za-z][A-Za-z0-9 /().&-]{2,40})\s*[:\-]\s*(.{2,})$", line)
            if match:
                key = match.group(1).lower().strip()
                if key in current and len(current) >= 2:
                    flush_current()
                current[key] = match.group(2).strip()
                continue
            flush_current()

        # Natural-language role patterns.
        for role in ROLE_WORDS:
            for line in lines:
                direct = re.match(rf"^(?:current\s+)?{re.escape(role)}\s*[:\-]\s*(.+)$", line, re.I)
                if direct and _looks_like_person_or_org(direct.group(1)):
                    facts.append(_fact(segment, "role", normalize_role(role), "held_by", direct.group(1).strip(), segment.title, 0.92, line))
            patterns = [
                rf"\b(?:the\s+)?{re.escape(role)}\s+(?:is|:|-)\s+({NAME_RE.pattern})",
                rf"({NAME_RE.pattern})\s+(?:is|serves as|acts as|appointed as|designated as)\s+(?:the\s+)?{re.escape(role)}\b",
                rf"\b{re.escape(role)}\s+({NAME_RE.pattern})",
            ]
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.I):
                    name = match.group(1).strip()
                    if not _looks_like_person_or_org(name):
                        continue
                    sentence = _sentence_around(text, match.start())
                    facts.append(_fact(segment, "role", normalize_role(role), "held_by", name, segment.title, 0.82, sentence))

        for contact in CONTACT_RE.findall(text):
            facts.append(_fact(segment, "contact", "contact", "value", contact, segment.title, 0.72, _sentence_around(text, text.find(contact))))
        for date in DATE_RE.findall(text):
            facts.append(_fact(segment, "event", "date", "value", date, segment.title, 0.68, _sentence_around(text, text.find(date))))

    return _dedupe_facts(facts)


def _sentence_around(text: str, pos: int) -> str:
    start = max(text.rfind(".", 0, pos), text.rfind("\n", 0, pos))
    end_candidates = [idx for idx in (text.find(".", pos + 1), text.find("\n", pos + 1)) if idx != -1]
    end = min(end_candidates) if end_candidates else min(len(text), pos + 500)
    return text[start + 1:end + 1].strip()


def _dedupe_facts(facts: list[ExtractedFact]) -> list[ExtractedFact]:
    seen = set()
    output = []
    for fact in facts:
        key = (fact.fact_type, fact.subject.lower(), fact.predicate.lower(), fact.object.lower(), fact.qualifier.lower())
        if key in seen:
            continue
        seen.add(key)
        output.append(fact)
    return output
