from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

from app.config import OPENAI_API_KEY, OPENAI_CHAT_MODEL, OPENAI_EMBEDDING_MODEL, VECTOR_DIR
from app.models.schemas import IngestedChunk, Source


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def _cosine(a: Counter, b: Counter) -> float:
    common = set(a) & set(b)
    numerator = sum(a[t] * b[t] for t in common)
    denom = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return numerator / denom if denom else 0.0


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

        query_vec = Counter(_tokens(query))
        scored = []
        for chunk in self._chunks.get(dataset_id, []):
            score = _cosine(query_vec, Counter(_tokens(chunk.text)))
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
                f"ragx_{dataset_id.replace('-', '_')}",
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
                f"ragx_{dataset_id.replace('-', '_')}",
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
