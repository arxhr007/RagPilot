from __future__ import annotations

import re

from app.models.schemas import ChatResponse
from app.orchestration.answering import dataset_vocabulary, find_fact_match, rerank_sources, synthesize_answer, validate_answer
from app.orchestration.query import understand_query
from app.rag.graph import graph_hint
from app.rag.hierarchical import hierarchical_index
from app.rag.keyword import keyword_index
from app.rag.semantic import semantic_index
from app.rag.sql import execute_sql, generate_fallback_sql, generate_sql, summarize_rows
from app.store import Dataset


SQL_HINTS = re.compile(r"\b(total|sum|average|avg|count|how many|top|highest|lowest|min|max|revenue|sales|by|list|show|which|owner|owns|team|endpoint|product|speaker|venue)\b", re.I)
GRAPH_HINTS = re.compile(r"\b(relationship|related|connect(?:ed|ion|s)?|dependency|depends|between|entity|graph|link(?:ed|s)?|programs?|associated|offers?)\b", re.I)
KEYWORD_HINTS = re.compile(r"\b(who is|where is|contact|email|phone|faculty|hod|principal|department|acronym|full form)\b", re.I)


def classify_query(dataset: Dataset, question: str, route_override: str = "auto") -> tuple[str, float, str]:
    if route_override != "auto":
        return route_override, 1.0, f"Manual route override selected: {route_override}."
    understood = understand_query(question, dataset_vocabulary(dataset))
    q = understood.expanded
    is_relationship = understood.intent == "relationship" or bool(GRAPH_HINTS.search(q))
    table_relationship = bool(re.search(r"\b(owner|owns|team|endpoint|venue|speaker|date|schedule|how many|count|list)\b", q, re.I))
    wants_sql = (bool(SQL_HINTS.search(q)) or understood.intent in {"aggregate", "list", "location", "time"} or (is_relationship and table_relationship)) and bool(dataset.tables)
    wants_graph = (understood.intent == "relationship" or bool(GRAPH_HINTS.search(q))) and bool(dataset.graph.get("nodes"))
    wants_keyword = understood.intent in {"point_lookup", "location", "time"} or bool(KEYWORD_HINTS.search(q))
    if wants_sql and dataset.chunks and any(w in question.lower() for w in ("why", "explain", "compare")):
        return "hybrid", 0.82, "Question has analytical language and may need narrative context."
    if wants_graph and not table_relationship:
        return "graph", 0.82, "Relationship-style phrasing matched extracted graph entities."
    if wants_graph and wants_sql:
        return "hybrid", 0.84, "Question has relationship wording plus structured table evidence."
    if wants_sql:
        return "sql", 0.9, "Numeric or aggregation phrasing matched available structured tables."
    if wants_keyword and (dataset.chunks or dataset.facts):
        if wants_graph and dataset.graph.get("nodes"):
            return "hybrid", 0.82, "Exact lookup and relationship signals matched keyword, semantic, and graph evidence."
        return "keyword", 0.88, "Exact lookup phrasing matched keyword/name retrieval."
    if wants_graph:
        return "graph", 0.74, "Relationship-style phrasing matched extracted entity graph."
    if any(segment.rag_module == "hierarchical" for segment in dataset.segments):
        return "hierarchical", 0.79, "Broad factual question can use section-level parent context."
    return "semantic", 0.84 if dataset.chunks else 0.35, "Factual long-form phrasing is best served by semantic retrieval."


def _merge_sources(*groups):
    seen = set()
    merged = []
    for group in groups:
        for source in group:
            key = (source.id, source.text[:80])
            if key in seen:
                continue
            seen.add(key)
            merged.append(source)
    return merged


def _best_table(dataset: Dataset, question: str):
    if not dataset.tables:
        return None
    q = question.lower()
    best = dataset.tables[0]
    best_score = -1
    for table in dataset.tables:
        columns = " ".join(table.columns).lower()
        source = table.source_name.lower()
        score = 0
        for term in re.findall(r"[a-zA-Z0-9_/-]+", q):
            if term in columns or term in source:
                score += 2
        if any(word in q for word in ("where", "venue", "location", "address")) and any(word in columns for word in ("venue", "location", "address")):
            score += 8
        if any(word in q for word in ("when", "date", "time", "schedule")) and any(word in columns for word in ("date", "time", "schedule")):
            score += 8
        if any(word in q for word in ("owner", "owns", "team")) and any(word in columns for word in ("owner", "team")):
            score += 8
        if any(word in q for word in ("speaker", "event")) and any(word in columns for word in ("speaker", "event")):
            score += 6
        if score > best_score:
            best = table
            best_score = score
    return best


def _estimate_context_budget(dataset: Dataset, sources, sql_rows) -> dict:
    dataset_chars = sum(len(chunk.text) for chunk in dataset.chunks)
    segment_chars = sum(len(segment.text) for segment in dataset.segments)
    table_chars = sum(
        len(" ".join(table.columns)) + (table.row_count * max(len(table.columns), 1) * 12)
        for table in dataset.tables
    )
    evidence_chars = sum(len(source.text) for source in sources)
    if sql_rows:
        evidence_chars += sum(len(" ".join(str(value) for value in row.values())) for row in sql_rows)
    dataset_tokens = max(0, (max(dataset_chars, segment_chars) + table_chars + 3) // 4)
    evidence_tokens = max(0, (evidence_chars + 3) // 4)
    saved_tokens = max(0, dataset_tokens - evidence_tokens)
    reduction = round((saved_tokens / dataset_tokens) * 100, 1) if dataset_tokens else 0
    return {
        "estimated_dataset_tokens": dataset_tokens,
        "estimated_evidence_tokens": evidence_tokens,
        "estimated_saved_tokens": saved_tokens,
        "reduction_percent": reduction,
    }


def answer_question(dataset: Dataset, question: str, route_override: str = "auto") -> ChatResponse:
    understood = understand_query(question, dataset_vocabulary(dataset))
    if understood.intent == "casual_chat":
        return ChatResponse(
            dataset_id=dataset.id,
            question=question,
            answer="Hi, I am ready. Ask me something from the uploaded data and I will answer with the best RAG route.",
            route="semantic",
            confidence=0.0,
            route_reason="Casual chat was detected, so retrieval was skipped.",
            normalized_query=understood.normalized,
            expanded_query=understood.expanded,
            query_intent=understood.intent,
            direct_answer="Hi, I am ready. Ask me something from the uploaded data and I will answer with the best RAG route.",
            answer_confidence=1.0,
            answer_validation={"status": "casual_chat", "reasons": ["The message was conversational, not a dataset question."]},
            candidate_count=0,
            retrievers_skipped=[{"retriever": "all", "reason": "Casual chat does not need retrieval."}],
            context_budget=_estimate_context_budget(dataset, [], []),
        )
    route, confidence, reason = classify_query(dataset, understood.normalized, route_override)
    sources = []
    generated_sql = None
    sql_rows = []
    graph = None
    answer_parts = []
    retrievers_used = []
    retrievers_skipped = []

    semantic_sources = []
    keyword_sources = []
    hierarchical_sources = []
    fact_match = find_fact_match(dataset, understood) if understood.intent in {"point_lookup", "location", "time"} else None

    if route in ("semantic", "hybrid", "graph"):
        if dataset.chunks:
            semantic_sources = semantic_index.search(dataset.id, understood.expanded, k=12)
            retrievers_used.append("semantic")
        else:
            retrievers_skipped.append({"retriever": "semantic", "reason": "No unstructured chunks are indexed."})

    if route in ("keyword", "hybrid"):
        if dataset.chunks:
            keyword_sources = keyword_index.search(dataset.id, understood.expanded, k=18)
            retrievers_used.append("keyword")
        else:
            retrievers_skipped.append({"retriever": "keyword", "reason": "No text chunks are indexed."})

    if route in ("hierarchical", "hybrid"):
        if dataset.segments:
            hierarchical_sources = hierarchical_index.search(dataset.id, understood.expanded, k=8)
            retrievers_used.append("hierarchical")
        else:
            retrievers_skipped.append({"retriever": "hierarchical", "reason": "No source segments are available."})

    if fact_match:
        retrievers_used.append("sql" if fact_match.fact_type in {"role", "contact", "event"} else "keyword")

    sources = _merge_sources(keyword_sources, hierarchical_sources, semantic_sources)
    candidate_count = len(sources) + (1 if fact_match else 0)
    reranked_sources = rerank_sources(understood, sources, fact_match)

    if route in ("sql", "hybrid") and dataset.tables:
        table = _best_table(dataset, understood.normalized)
        generated_sql = generate_sql(understood.normalized, table.table_name, table.columns)
        sql_rows = execute_sql(table.db_path, generated_sql)
        if not sql_rows:
            fallback_sql = generate_fallback_sql(understood.normalized, table.table_name, table.columns)
            if fallback_sql != generated_sql:
                fallback_rows = execute_sql(table.db_path, fallback_sql)
                if fallback_rows:
                    generated_sql = fallback_sql
                    sql_rows = fallback_rows
        answer_parts.append(summarize_rows(question, generated_sql, sql_rows))
        retrievers_used.append("sql")
    elif route == "sql":
        retrievers_skipped.append({"retriever": "sql", "reason": "No reliable SQLite tables exist for this dataset."})

    if route in ("graph", "hybrid"):
        graph = dataset.graph
        answer_parts.append(graph_hint(question, graph))
        if graph.get("nodes"):
            retrievers_used.append("graph")
        else:
            retrievers_skipped.append({"retriever": "graph", "reason": "No graph entities were extracted."})

    direct_answer, synthesized, answer_confidence = synthesize_answer(understood, reranked_sources, fact_match)
    if sql_rows:
        answer_confidence = max(answer_confidence, 0.86)
        if not direct_answer:
            direct_answer = summarize_rows(question, generated_sql or "", sql_rows)
    if route in ("keyword", "semantic", "hybrid", "graph", "hierarchical") or fact_match:
        answer_parts.append(synthesized)

    answer = "\n\n".join(part for part in answer_parts if part).strip()
    if not answer:
        answer = "RAGX needs at least one ingested document, table, or URL before it can answer grounded questions."
        answer_confidence = 0.0

    validation = validate_answer(understood, answer, reranked_sources, fact_match, answer_confidence)
    if validation.get("status") == "not_found":
        answer = "I could not find that in the uploaded data."

    return ChatResponse(
        dataset_id=dataset.id,
        question=question,
        answer=answer,
        route=route,
        confidence=confidence,
        route_reason=reason,
        normalized_query=understood.normalized,
        expanded_query=understood.expanded,
        query_intent=understood.intent,
        direct_answer=direct_answer,
        answer_confidence=answer_confidence,
        answer_validation=validation,
        sources=reranked_sources,
        reranked_sources=reranked_sources,
        candidate_count=candidate_count,
        fact_match=fact_match,
        generated_sql=generated_sql,
        sql_rows=sql_rows,
        graph=graph,
        retrievers_used=list(dict.fromkeys(retrievers_used)),
        retrievers_skipped=retrievers_skipped,
        context_budget=_estimate_context_budget(dataset, reranked_sources, sql_rows),
    )
