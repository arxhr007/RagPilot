from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from app.models.schemas import IngestedChunk, Source


TOKEN_RE = re.compile(r"[A-Za-z0-9_.'-]+")
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "by", "for", "from", "in", "is", "it",
    "of", "on", "or", "the", "to", "what", "where", "when", "who", "which",
    "with", "about", "all", "show", "list",
}


def tokens(text: str) -> list[str]:
    cleaned = [token.lower().strip(".'-") for token in TOKEN_RE.findall(text)]
    return [token for token in cleaned if len(token) > 1 and token not in STOPWORDS]


class KeywordIndex:
    def __init__(self) -> None:
        self._chunks: dict[str, list[IngestedChunk]] = {}
        self._chunk_ids: dict[str, set[str]] = {}

    def add(self, dataset_id: str, chunks: list[IngestedChunk]) -> None:
        seen = self._chunk_ids.setdefault(dataset_id, set())
        bucket = self._chunks.setdefault(dataset_id, [])
        for chunk in chunks:
            if chunk.id in seen:
                continue
            seen.add(chunk.id)
            bucket.append(chunk)

    def search(self, dataset_id: str, query: str, k: int = 6) -> list[Source]:
        chunks = self._chunks.get(dataset_id, [])
        if not chunks:
            return []
        query_terms = tokens(query)
        query_counts = Counter(query_terms)
        doc_freq: defaultdict[str, int] = defaultdict(int)
        chunk_terms = []
        for chunk in chunks:
            terms = tokens(chunk.text)
            chunk_terms.append(terms)
            for term in set(terms):
                doc_freq[term] += 1

        scored: list[Source] = []
        total_docs = len(chunks)
        phrase = query.lower().strip()
        for chunk, terms in zip(chunks, chunk_terms):
            counts = Counter(terms)
            score = 0.0
            for term, q_count in query_counts.items():
                if term not in counts:
                    continue
                idf = math.log((total_docs + 1) / (doc_freq[term] + 0.5)) + 1
                score += counts[term] * idf * q_count
            if phrase and phrase in chunk.text.lower():
                score += 12
            if score > 0:
                scored.append(chunk.source.model_copy(update={"score": round(score, 4)}))
        scored.sort(key=lambda source: source.score, reverse=True)
        return scored[:k]

    def extractive_answer(self, question: str, sources: list[Source]) -> str:
        if not sources:
            return "I could not find a strong exact-match source for that question."
        q_terms = set(tokens(question))
        sentences = []
        for source_index, source in enumerate(sources, start=1):
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", source.text):
                clean = sentence.strip()
                if len(clean) < 30:
                    continue
                overlap = len(q_terms & set(tokens(clean)))
                if overlap:
                    sentences.append((overlap, source_index, clean))
        sentences.sort(key=lambda item: item[0], reverse=True)
        if not sentences:
            return f"Closest exact-match source: {sources[0].text[:500]} [1]"
        picked = sentences[:4]
        return " ".join(f"{sentence} [{source_index}]" for _, source_index, sentence in picked)


keyword_index = KeywordIndex()
