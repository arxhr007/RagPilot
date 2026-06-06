from __future__ import annotations

import re
from collections import Counter
from uuid import uuid4

from app.models.schemas import Segment


HEADING_RE = re.compile(r"^(#{1,6}\s+.+|[A-Z][A-Z0-9 &/().,-]{5,}|.{1,80}:)$")
ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z.&'-]+(?:\s+[A-Z][A-Za-z.&'-]+){1,3}\b")
KEY_VALUE_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 /().&-]{2,40})\s*[:\-]\s*(.{2,})$")


def _title_from_lines(lines: list[str], fallback: str) -> str:
    for line in lines[:5]:
        clean = line.strip(" #:\t")
        if 3 <= len(clean) <= 90:
            return clean
    return fallback


def split_sections(text: str, source_name: str) -> list[tuple[str, str]]:
    lines = [line.rstrip() for line in text.splitlines()]
    sections: list[tuple[str, list[str]]] = []
    current_title = source_name
    current: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                current.append("")
            continue
        is_heading = bool(HEADING_RE.match(stripped)) and len(stripped.split()) <= 12
        if is_heading and len("\n".join(current).strip()) > 120:
            sections.append((current_title, current))
            current_title = stripped.strip(" #:\t")
            current = [line]
        else:
            if not current and is_heading:
                current_title = stripped.strip(" #:\t")
            current.append(line)

    if current:
        sections.append((current_title, current))

    merged: list[tuple[str, str]] = []
    for title, block_lines in sections:
        block = "\n".join(block_lines).strip()
        if not block:
            continue
        if len(block) < 240 and merged:
            prev_title, prev_text = merged[-1]
            merged[-1] = (prev_title, f"{prev_text}\n\n{block}")
        else:
            merged.append((title or _title_from_lines(block_lines, source_name), block))
    return merged or [(source_name, text)]


def _pipe_table_score(lines: list[str]) -> float:
    pipe_lines = [line for line in lines if line.count("|") >= 2]
    if len(pipe_lines) < 2:
        return 0.0
    widths = [line.count("|") for line in pipe_lines[:8]]
    consistent = Counter(widths).most_common(1)[0][1] / len(widths)
    return min(0.95, 0.45 + consistent * 0.45 + min(len(pipe_lines), 10) * 0.01)


def _key_value_score(lines: list[str]) -> float:
    kv_lines = [line for line in lines if KEY_VALUE_RE.match(line)]
    if len(kv_lines) < 4:
        return 0.0
    density = len(kv_lines) / max(1, len([line for line in lines if line.strip()]))
    return min(0.88, 0.35 + density * 0.5)


def _csv_like_score(lines: list[str]) -> float:
    comma_lines = [line for line in lines if line.count(",") >= 2]
    if len(comma_lines) < 3:
        return 0.0
    widths = [line.count(",") for line in comma_lines[:10]]
    consistent = Counter(widths).most_common(1)[0][1] / len(widths)
    return min(0.9, 0.35 + consistent * 0.45)


def _entity_score(text: str) -> tuple[float, int]:
    entities = {entity.strip() for entity in ENTITY_RE.findall(text) if len(entity.strip()) > 4}
    density = len(entities) / max(1, len(text.split()) / 120)
    return min(0.92, density / 8), len(entities)


def classify_segment(text: str) -> tuple[str, str, float, list[str]]:
    lines = [line for line in text.splitlines() if line.strip()]
    pipe_score = _pipe_table_score(lines)
    csv_score = _csv_like_score(lines)
    kv_score = _key_value_score(lines)
    entity_score, entity_count = _entity_score(text)
    reasons: list[str] = []

    table_score = max(pipe_score, csv_score, kv_score)
    if table_score >= 0.72:
        reasons.append("Reliable repeated table-like structure was detected.")
        return "sql_candidate", "sql", table_score, reasons

    if entity_score >= 0.45 and entity_count >= 8:
        reasons.append(f"Entity-heavy section detected with about {entity_count} named entities.")
        return "graph_candidate", "graph", entity_score, reasons

    if len(text) > 1800:
        reasons.append("Long section benefits from parent-child section context.")
        return "hierarchical_parent", "hierarchical", 0.76, reasons

    if any(marker in text.lower() for marker in ("phone", "email", "contact", "faculty", "department", "admission", "ktu", "naac")):
        reasons.append("Exact names, acronyms, or institutional terms benefit from keyword retrieval.")
        return "keyword_candidate", "keyword", 0.7, reasons

    reasons.append("Narrative or descriptive text is best suited to semantic retrieval.")
    return "semantic", "semantic", 0.74, reasons


def segment_text(text: str, source_name: str, input_id: str) -> list[Segment]:
    segments: list[Segment] = []
    for index, (title, section_text) in enumerate(split_sections(text, source_name)):
        segment_type, rag_module, confidence, reasons = classify_segment(section_text)
        segments.append(
            Segment(
                id=f"{input_id}:segment:{index}",
                source_name=source_name,
                title=title[:90],
                segment_type=segment_type,
                rag_module=rag_module,
                confidence=round(confidence, 2),
                reasons=reasons,
                text_preview=" ".join(section_text.split())[:360],
                text=section_text,
                metadata={"input_id": input_id, "ordinal": index},
            )
        )
    return segments


def segment_table_input(source_name: str, input_id: str, table_name: str, columns: list[str], row_count: int) -> Segment:
    return Segment(
        id=f"{input_id}:segment:table",
        source_name=source_name,
        title=source_name,
        segment_type="structured_table",
        rag_module="sql",
        confidence=0.96,
        reasons=["CSV/XLSX input was directly loaded as a structured SQLite table."],
        text_preview=f"{row_count} rows with columns: {', '.join(columns[:10])}",
        table_name=table_name,
        metadata={
            "input_id": input_id,
            "columns": columns,
            "row_count": row_count,
            "classifier": "heuristic",
            "primary_rag": "sql",
            "secondary_rags": [],
            "signals": ["structured file", "tabular columns", "row count"],
            "decision_reason": "CSV/XLSX input was directly loaded as a reliable SQLite table.",
        },
    )
