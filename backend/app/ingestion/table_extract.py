from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pandas as pd

from app.config import SQLITE_DIR
from app.models.schemas import Segment
from app.rag.sql import load_dataframe
from app.store import TableInfo


def _clean_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().strip("|")).strip()


def _dedupe_columns(columns: list[str]) -> list[str]:
    output = []
    seen: dict[str, int] = {}
    for idx, column in enumerate(columns):
        base = re.sub(r"[^A-Za-z0-9_]+", "_", column.strip().lower()).strip("_") or f"column_{idx + 1}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        output.append(base if count == 0 else f"{base}_{count + 1}")
    return output


def _pipe_table(segment: Segment) -> pd.DataFrame | None:
    rows = []
    for line in segment.text.splitlines():
        if line.count("|") < 2:
            continue
        cells = [_clean_cell(cell) for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and not all(re.fullmatch(r"[-: ]+", cell) for cell in cells):
            rows.append(cells)
    if len(rows) < 2:
        return None
    width = max(set(len(row) for row in rows), key=[len(row) for row in rows].count)
    rows = [row for row in rows if len(row) == width]
    if len(rows) < 2:
        return None
    columns = _dedupe_columns(rows[0])
    return pd.DataFrame(rows[1:], columns=columns)


def _csv_table(segment: Segment) -> pd.DataFrame | None:
    lines = [line for line in segment.text.splitlines() if line.count(",") >= 2]
    if len(lines) < 3:
        return None
    rows = [[_clean_cell(cell) for cell in line.split(",")] for line in lines]
    width = max(set(len(row) for row in rows), key=[len(row) for row in rows].count)
    rows = [row for row in rows if len(row) == width]
    if len(rows) < 3:
        return None
    return pd.DataFrame(rows[1:], columns=_dedupe_columns(rows[0]))


def _key_value_records(segment: Segment) -> pd.DataFrame | None:
    records = []
    current: dict[str, str] = {}
    for line in segment.text.splitlines():
        stripped = line.strip()
        if not stripped:
            if len(current) >= 2:
                records.append(current)
            current = {}
            continue
        match = re.match(r"^([A-Za-z][A-Za-z0-9 /().&-]{2,40})\s*[:\-]\s*(.{2,})$", stripped)
        if not match:
            continue
        key = _dedupe_columns([match.group(1)])[0]
        if key in current and len(current) >= 2:
            records.append(current)
            current = {}
        current[key] = _clean_cell(match.group(2))
    if len(current) >= 2:
        records.append(current)
    if len(records) < 2:
        return None
    common = CounterKey(records)
    if len(common) < 2:
        return None
    return pd.DataFrame(records)


def CounterKey(records: list[dict[str, str]]) -> set[str]:
    counts: dict[str, int] = {}
    for record in records:
        for key in record:
            counts[key] = counts.get(key, 0) + 1
    return {key for key, count in counts.items() if count >= 2}


def dataframe_from_segment(segment: Segment) -> pd.DataFrame | None:
    if segment.segment_type != "sql_candidate" or segment.confidence < 0.72:
        return None
    for parser in (_pipe_table, _csv_table, _key_value_records):
        df = parser(segment)
        if df is not None and len(df) >= 1 and len(df.columns) >= 2:
            return df
    return None


def load_text_tables(dataset_id: str, source_name: str, segments: Iterable[Segment]) -> list[TableInfo]:
    tables: list[TableInfo] = []
    for index, segment in enumerate(segments):
        df = dataframe_from_segment(segment)
        if df is None:
            continue
        table_name = f"text_table_{segment.id.split(':')[0].replace('-', '_')[:8]}_{index}"
        db_path = SQLITE_DIR / f"{dataset_id}.db"
        load_dataframe(df, db_path, table_name)
        segment.table_name = table_name
        tables.append(
            TableInfo(
                input_id=segment.metadata.get("input_id", segment.id),
                table_name=table_name,
                db_path=db_path,
                columns=[str(column) for column in df.columns],
                row_count=len(df),
                source_name=source_name,
                derived_from_segment=segment.id,
            )
        )
    return tables
