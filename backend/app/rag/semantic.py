from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Iterable

from app.config import OPENAI_API_KEY, OPENAI_CHAT_MODEL, OPENAI_EMBEDDING_MODEL, VECTOR_DIR
from app.models.schemas import IngestedChunk, Source


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def _idf_cosine(query_counts: Counter, doc_counts: Counter, idf: dict[str, float]) -> float:
    common = set(query_counts) & set(doc_counts)
    numerator = sum(query_counts[t] * doc_counts[t] * (idf.get(t, 1.0) ** 2) for t in common)
    q_norm = math.sqrt(sum((query_counts[t] * idf.get(t, 1.0)) ** 2 for t in query_counts))
    d_norm = math.sqrt(sum((doc_counts[t] * idf.get(t, 1.0)) ** 2 for t in doc_counts))
    return numerator / (q_norm * d_norm) if q_norm and d_norm else 0.0


class SemanticIndex:
    def __init__(self) -> None:
        self._chunks: dict[str, list[IngestedChunk]] = {}
        self._chunk_ids: dict[str, set[str]] = {}

    def add(self, dataset_id: str, chunks: Iterable[IngestedChunk]) -> None:
        new_chunks = []
        seen = self._chunk_ids.setdefault(dataset_id, set())
        for chunk in chunks:
            if chunk.id in seen:
                continue
            seen.add(chunk.id)
            new_chunks.append(chunk)
        self._chunks.setdefault(dataset_id, []).extend(new_chunks)
        self._try_chroma_add(dataset_id, new_chunks)

    def search(self, dataset_id: str, query: str, k: int = 5) -> list[Source]:
        chroma_hits = self._try_chroma_search(dataset_id, query, k)
        if chroma_hits:
            return chroma_hits

        chunks = self._chunks.get(dataset_id, [])
        query_counts = Counter(_tokens(query))
        if not chunks or not query_counts:
            return []

        doc_counts = [Counter(_tokens(chunk.text)) for chunk in chunks]
        doc_freq: defaultdict[str, int] = defaultdict(int)
        for counts in doc_counts:
            for term in counts:
                doc_freq[term] += 1
        total_docs = len(chunks)
        idf = {term: math.log((total_docs + 1) / (freq + 0.5)) + 1 for term, freq in doc_freq.items()}

        scored = []
        for chunk, counts in zip(chunks, doc_counts):
            score = _idf_cosine(query_counts, counts, idf)
            if score > 0:
                source = chunk.source.model_copy(update={"score": round(score, 4)})
                scored.append(source)
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:k]

    def answer(self, question: str, sources: list[Source]) -> str:
        context = "\n\n".join(f"[{i+1}] {s.text}" for i, s in enumerate(sources))
        if OPENAI_API_KEY and sources:
            try:
                from openai import OpenAI

                client = OpenAI(api_key=OPENAI_API_KEY)
                response = client.chat.completions.create(
                    model=OPENAI_CHAT_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": "Answer only from the provided context. Cite sources as [1], [2]. If missing, say what is missing.",
                        },
                        {"role": "user", "content": f"Question: {question}\n\nContext:\n{context}"},
                    ],
                    temperature=0.1,
                )
                return response.choices[0].message.content or ""
            except Exception:
                pass
        if not sources:
            return "I could not find enough grounded context in the indexed sources."
        return f"Based on the strongest retrieved source: {sources[0].text[:700]} [1]"

    def _try_chroma_add(self, dataset_id: str, chunks: list[IngestedChunk]) -> None:
        if not OPENAI_API_KEY or not chunks:
            return
        try:
            import chromadb
            from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

            client = chromadb.PersistentClient(path=str(VECTOR_DIR))
            collection = client.get_or_create_collection(
                f"RAGPilot_{dataset_id.replace('-', '_')}",
                embedding_function=OpenAIEmbeddingFunction(
                    api_key=OPENAI_API_KEY,
                    model_name=OPENAI_EMBEDDING_MODEL,
                ),
            )
            collection.upsert(
                ids=[c.id for c in chunks],
                documents=[c.text for c in chunks],
                metadatas=[
                    {
                        "source_id": c.source.id,
                        "title": c.source.title,
                        "url": c.source.url or "",
                        "file_name": c.source.file_name or "",
                    }
                    for c in chunks
                ],
            )
        except Exception:
            return

    def _try_chroma_search(self, dataset_id: str, query: str, k: int) -> list[Source]:
        if not OPENAI_API_KEY:
            return []
        try:
            import chromadb
            from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

            client = chromadb.PersistentClient(path=str(VECTOR_DIR))
            collection = client.get_collection(
                f"RAGPilot_{dataset_id.replace('-', '_')}",
                embedding_function=OpenAIEmbeddingFunction(
                    api_key=OPENAI_API_KEY,
                    model_name=OPENAI_EMBEDDING_MODEL,
                ),
            )
            results = collection.query(query_texts=[query], n_results=k)
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]
            sources = []
            for idx, doc in enumerate(docs):
                meta = metas[idx] if idx < len(metas) else {}
                distance = distances[idx] if idx < len(distances) else 1
                sources.append(
                    Source(
                        id=meta.get("source_id", f"chroma:{idx}"),
                        title=meta.get("title", ""),
                        url=meta.get("url") or None,
                        file_name=meta.get("file_name") or None,
                        text=doc,
                        score=round(1 / (1 + float(distance)), 4),
                    )
                )
            return sources
        except Exception:
            return []


semantic_index = SemanticIndex()
