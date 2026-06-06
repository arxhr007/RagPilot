from __future__ import annotations

from app.models.schemas import Segment, Source
from app.rag.keyword import tokens


class HierarchicalIndex:
    def __init__(self) -> None:
        self._segments: dict[str, list[Segment]] = {}

    def add(self, dataset_id: str, segments: list[Segment]) -> None:
        self._segments[dataset_id] = segments

    def search(self, dataset_id: str, query: str, k: int = 4) -> list[Source]:
        query_terms = set(tokens(query))
        scored: list[Source] = []
        for segment in self._segments.get(dataset_id, []):
            if segment.rag_module == "sql":
                continue
            section_terms = set(tokens(segment.title + " " + segment.text))
            overlap = len(query_terms & section_terms)
            if overlap == 0:
                continue
            score = overlap + (0.5 if segment.rag_module == "hierarchical" else 0)
            scored.append(
                Source(
                    id=segment.id,
                    title=segment.title,
                    file_name=segment.source_name,
                    text=segment.text[:1600],
                    score=round(score, 4),
                )
            )
        scored.sort(key=lambda source: source.score, reverse=True)
        return scored[:k]


hierarchical_index = HierarchicalIndex()
