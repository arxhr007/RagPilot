from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models.schemas import Architecture, DatasetAnalysis, ExtractedFact, IngestedChunk, Segment


@dataclass
class TableInfo:
    input_id: str
    table_name: str
    db_path: Path
    columns: list[str]
    row_count: int
    source_name: str
    derived_from_segment: str | None = None


@dataclass
class Dataset:
    id: str
    name: str
    inputs: list[dict[str, Any]] = field(default_factory=list)
    chunks: list[IngestedChunk] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    facts: list[ExtractedFact] = field(default_factory=list)
    tables: list[TableInfo] = field(default_factory=list)
    graph: dict[str, Any] = field(default_factory=lambda: {"nodes": [], "edges": []})
    analysis: DatasetAnalysis | None = None
    architecture: Architecture | None = None


class DatasetStore:
    def __init__(self) -> None:
        self.datasets: dict[str, Dataset] = {}

    def create(self, name: str = "RAGX Dataset") -> Dataset:
        dataset = Dataset(id=str(uuid4()), name=name)
        self.datasets[dataset.id] = dataset
        return dataset

    def get(self, dataset_id: str) -> Dataset:
        if dataset_id not in self.datasets:
            raise KeyError(f"Dataset {dataset_id} was not found")
        return self.datasets[dataset_id]


store = DatasetStore()
