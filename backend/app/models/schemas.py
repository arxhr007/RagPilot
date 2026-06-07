from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Literal


RagStrategy = Literal["semantic", "sql", "graph", "keyword", "hierarchical", "hybrid"]
RouteOverride = Literal["auto", "semantic", "sql", "graph", "keyword", "hierarchical", "hybrid"]


class Segment(BaseModel):
    id: str
    source_name: str
    title: str
    segment_type: str
    rag_module: RagStrategy
    confidence: float
    reasons: list[str]
    text_preview: str
    text: str = ""
    table_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Source(BaseModel):
    id: str
    title: str = ""
    url: str | None = None
    file_name: str | None = None
    text: str = ""
    score: float = 0.0
    match_reason: str = ""


class ExtractedFact(BaseModel):
    id: str
    fact_type: str
    subject: str
    predicate: str
    object: str
    qualifier: str = ""
    source_id: str
    source_name: str
    confidence: float = 0.0
    text: str = ""


class IngestedChunk(BaseModel):
    id: str
    dataset_id: str
    input_id: str
    text: str
    source: Source
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetAnalysis(BaseModel):
    dataset_id: str
    detected_inputs: list[dict[str, Any]]
    characteristics: dict[str, Any]
    selected_strategy: RagStrategy
    confidence: float
    reasons: list[str]
    tradeoffs: list[str] = Field(default_factory=list)
    activated_nodes: list[str] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    rag_modes_available: list[RagStrategy] = Field(default_factory=list)
    rag_modes_selected: list[RagStrategy] = Field(default_factory=list)
    detected_tables: list[dict[str, Any]] = Field(default_factory=list)
    entity_types: dict[str, int] = Field(default_factory=dict)
    graph: dict[str, Any] = Field(default_factory=dict)
    method_assignments: list[dict[str, Any]] = Field(default_factory=list)
    route_policy_summary: str = ""
    rag_classification_summary: dict[str, Any] = Field(default_factory=dict)
    question_suggestions: list[str] = Field(default_factory=list)
    question_suggestion_source: str = ""
    token_metrics: dict[str, Any] = Field(default_factory=dict)


class Architecture(BaseModel):
    dataset_id: str
    name: str
    modules: list[dict[str, Any]]
    workflow_nodes: list[str]
    explanation: str


class ChatRequest(BaseModel):
    dataset_id: str
    question: str
    route_override: RouteOverride = "auto"


class ChatResponse(BaseModel):
    dataset_id: str
    question: str
    answer: str
    route: RagStrategy
    confidence: float
    route_reason: str
    normalized_query: str = ""
    expanded_query: str = ""
    query_intent: str = "factual"
    direct_answer: str = ""
    answer_confidence: float = 0.0
    answer_validation: dict[str, Any] = Field(default_factory=dict)
    sources: list[Source] = Field(default_factory=list)
    reranked_sources: list[Source] = Field(default_factory=list)
    candidate_count: int = 0
    fact_match: ExtractedFact | None = None
    generated_sql: str | None = None
    sql_rows: list[dict[str, Any]] = Field(default_factory=list)
    graph: dict[str, Any] | None = None
    retrievers_used: list[RagStrategy] = Field(default_factory=list)
    retrievers_skipped: list[dict[str, str]] = Field(default_factory=list)
    context_budget: dict[str, Any] = Field(default_factory=dict)


class UrlIngestRequest(BaseModel):
    url: str
    max_pages: int = 8
    use_playwright: bool = True
