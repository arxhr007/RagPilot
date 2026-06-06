from __future__ import annotations

from collections import Counter

from app.models.schemas import Architecture, DatasetAnalysis
from app.analysis.rag_classifier import classification_counts
from app.store import Dataset


def analyze_dataset(dataset: Dataset) -> DatasetAnalysis:
    has_tables = bool(dataset.tables)
    has_text = bool(dataset.chunks)
    has_web = any(item.get("kind") == "website" for item in dataset.inputs)
    has_graph = len(dataset.graph.get("nodes", [])) >= 3
    selected_modes = sorted({segment.rag_module for segment in dataset.segments})
    if has_tables and "sql" not in selected_modes:
        selected_modes.append("sql")
    if has_text and "semantic" not in selected_modes:
        selected_modes.append("semantic")
    if has_graph and "graph" not in selected_modes:
        selected_modes.append("graph")
    input_count = len(dataset.inputs)

    if len(selected_modes) >= 2:
        strategy = "hybrid"
        confidence = 0.91
    elif has_tables:
        strategy = "sql"
        confidence = 0.88
    elif has_graph:
        strategy = "graph"
        confidence = 0.72
    else:
        strategy = "semantic"
        confidence = 0.84 if has_text else 0.4

    reasons = []
    if has_tables:
        text_derived = [table for table in dataset.tables if table.derived_from_segment]
        if text_derived:
            reasons.append(f"{len(text_derived)} reliable text-derived table(s) were converted to SQLite.")
        else:
            reasons.append("Structured tabular input was detected and loaded into SQLite.")
    if has_text:
        reasons.append("Unstructured text chunks are available for semantic retrieval.")
    if any(segment.rag_module == "keyword" for segment in dataset.segments):
        reasons.append("Keyword retrieval is active for exact names, acronyms, and institutional terms.")
    if any(segment.rag_module == "hierarchical" for segment in dataset.segments):
        reasons.append("Hierarchical retrieval is active for long sections that need parent context.")
    if has_web:
        reasons.append("Website pages were ingested through the refactored scraper pipeline.")
    if has_graph:
        reasons.append("Entity co-occurrences were extracted for graph-style inspection.")
    if not reasons:
        reasons.append("No usable inputs have been ingested yet.")

    activated = ["analyze_dataset", "segment_dataset", "select_strategy", "build_pipeline"]
    if has_text:
        activated.append("semantic_index")
    if has_tables:
        activated.append("sqlite_loader")
    if has_graph:
        activated.append("graph_layer")
    if any(segment.rag_module == "keyword" for segment in dataset.segments):
        activated.append("keyword_rag")
    if any(segment.rag_module == "hierarchical" for segment in dataset.segments):
        activated.append("hierarchical_rag")

    detected_tables = [
        {
            "table_name": table.table_name,
            "columns": table.columns,
            "row_count": table.row_count,
            "source_name": table.source_name,
            "derived_from_segment": table.derived_from_segment,
        }
        for table in dataset.tables
    ]
    entity_types = dataset.graph.get("entity_types", {})
    method_assignments = [
        {
            "title": segment.title,
            "source_name": segment.source_name,
            "segment_type": segment.segment_type,
            "method": segment.rag_module,
            "primary_rag": segment.metadata.get("primary_rag", segment.rag_module),
            "secondary_rags": segment.metadata.get("secondary_rags", []),
            "confidence": segment.confidence,
            "reason": " ".join(segment.reasons),
            "classifier": segment.metadata.get("classifier", "heuristic"),
            "signals": segment.metadata.get("signals", []),
            "decision_reason": segment.metadata.get("decision_reason", " ".join(segment.reasons)),
            "table_name": segment.table_name,
        }
        for segment in dataset.segments
    ]
    rag_counts = classification_counts(dataset.segments)
    dataset_chars = sum(len(getattr(chunk, "text", "")) for chunk in dataset.chunks)
    segment_chars = sum(len(segment.text) for segment in dataset.segments)
    table_chars = sum(
        len(" ".join(table.columns)) + (table.row_count * max(len(table.columns), 1) * 12)
        for table in dataset.tables
    )
    estimated_dataset_tokens = max(1, (max(dataset_chars, segment_chars) + table_chars + 3) // 4) if (dataset_chars or segment_chars or table_chars) else 0

    return DatasetAnalysis(
        dataset_id=dataset.id,
        detected_inputs=dataset.inputs,
        characteristics={
            "input_count": input_count,
            "has_tables": has_tables,
            "has_unstructured_text": has_text,
            "has_website_content": has_web,
            "entity_count": len(dataset.graph.get("nodes", [])),
            "relationship_count": len(dataset.graph.get("edges", [])),
            "table_count": len(dataset.tables),
            "chunk_count": len(dataset.chunks),
            "segment_count": len(dataset.segments),
            "semantic_segment_count": sum(1 for segment in dataset.segments if segment.rag_module == "semantic"),
            "sql_segment_count": sum(1 for segment in dataset.segments if segment.rag_module == "sql"),
            "graph_segment_count": sum(1 for segment in dataset.segments if segment.rag_module == "graph"),
            "keyword_segment_count": sum(1 for segment in dataset.segments if segment.rag_module == "keyword"),
            "hierarchical_segment_count": sum(1 for segment in dataset.segments if segment.rag_module == "hierarchical"),
        },
        selected_strategy=strategy,
        confidence=confidence,
        reasons=reasons,
        tradeoffs=[
            "Graph retrieval is intentionally lightweight for MVP reliability.",
            "Semantic search falls back to local lexical ranking when OpenAI or ChromaDB is unavailable.",
        ],
        activated_nodes=activated,
        segments=dataset.segments,
        rag_modes_available=["semantic", "sql", "graph", "keyword", "hierarchical", "hybrid"],
        rag_modes_selected=selected_modes or [strategy],
        detected_tables=detected_tables,
        entity_types=entity_types,
        graph=dataset.graph,
        method_assignments=method_assignments,
        route_policy_summary="Auto routing uses SQL for reliable tables, keyword for exact names/acronyms, graph for relationships, hierarchical for long sections, semantic for factual prose, and hybrid when evidence spans modes.",
        rag_classification_summary={
            "counts": rag_counts,
            "classifier_sources": dict(Counter(str(segment.metadata.get("classifier", "heuristic")) for segment in dataset.segments)),
            "warnings": [
                "SQL is only activated for CSV/XLSX inputs or high-confidence repeated table-like text.",
            ],
        },
        token_metrics={
            "estimated_dataset_tokens": estimated_dataset_tokens,
            "estimated_chunk_count": len(dataset.chunks),
            "estimated_table_tokens": (table_chars + 3) // 4 if table_chars else 0,
        },
    )


def build_architecture(dataset: Dataset) -> Architecture:
    analysis = dataset.analysis or analyze_dataset(dataset)
    modules = []
    if dataset.chunks:
        modules.append({"name": "Semantic RAG", "status": "active", "backend": "ChromaDB with lexical fallback"})
    if dataset.tables:
        modules.append({"name": "SQL RAG", "status": "active", "backend": "SQLite"})
    if dataset.graph.get("nodes"):
        modules.append({"name": "Graph Layer", "status": "active", "backend": "Entity co-occurrence graph"})
    if any(segment.rag_module == "keyword" for segment in dataset.segments):
        modules.append({"name": "Keyword/BM25 RAG", "status": "active", "backend": "Local lexical index"})
    if any(segment.rag_module == "hierarchical" for segment in dataset.segments):
        modules.append({"name": "Hierarchical RAG", "status": "active", "backend": "Section parent context"})
    if not modules:
        modules.append({"name": "Ingestion", "status": "waiting_for_data"})

    return Architecture(
        dataset_id=dataset.id,
        name=f"{analysis.selected_strategy.title()} Multi-RAG Architecture",
        modules=modules,
        workflow_nodes=analysis.activated_nodes + [
            "classify_query",
            "route_query",
            "synthesize_answer",
        ],
        explanation="RAGX selected this architecture from detected modality, table presence, and entity relationships.",
    )
