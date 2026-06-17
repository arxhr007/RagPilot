from __future__ import annotations

from pathlib import Path
import re
import sqlite3
from typing import Any

import pandas as pd

from app.config import OPENAI_API_KEY, OPENAI_CHAT_MODEL


AGG_WORDS = {
    "count": "COUNT(*)",
    "total": "SUM",
    "sum": "SUM",
    "average": "AVG",
    "avg": "AVG",
    "maximum": "MAX",
    "max": "MAX",
    "minimum": "MIN",
    "min": "MIN",
}


def load_dataframe(df: pd.DataFrame, db_path: Path, table_name: str) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        df.to_sql(table_name, conn, if_exists="replace", index=False)


def is_read_only_sql(sql: str) -> bool:
    normalized = sql.strip().strip(";").lower()
    forbidden = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|pragma|vacuum)\b", re.I)
    return normalized.startswith("select") and not forbidden.search(normalized)


def _clean_sql(raw: str) -> str:
    sql = (raw or "").strip()
    if sql.startswith("```"):
        sql = re.sub(r"^```[a-zA-Z]*\s*", "", sql)
        sql = re.sub(r"\s*```$", "", sql)
    return sql.strip().strip("`").strip()


def generate_sql(question: str, table_name: str, columns: list[str], use_openai: bool = True) -> str:
    if OPENAI_API_KEY and use_openai:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=OPENAI_API_KEY)
            response = client.chat.completions.create(
                model=OPENAI_CHAT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "Generate one SQLite SELECT query only. No markdown. Use only the provided table and columns.",
                    },
                    {
                        "role": "user",
                        "content": f"Table: {table_name}\nColumns: {columns}\nQuestion: {question}",
                    },
                ],
                temperature=0,
            )
            sql = _clean_sql(response.choices[0].message.content or "")
            if is_read_only_sql(sql):
                return sql.rstrip(";")
        except Exception:
            pass

    return generate_fallback_sql(question, table_name, columns)


def generate_fallback_sql(question: str, table_name: str, columns: list[str]) -> str:
    q = question.lower()
    numeric_columns = [c for c in columns if re.search(r"amount|price|sales|revenue|total|score|count|qty|quantity|value|cost", c, re.I)]
    first_col = columns[0] if columns else "*"
    metric = numeric_columns[0] if numeric_columns else first_col
    if "count" in q or "how many" in q:
        return f'SELECT COUNT(*) AS count FROM "{table_name}"'
    if any(word in q for word in ("average", "avg", "mean")):
        return f'SELECT AVG("{metric}") AS average_{metric} FROM "{table_name}"'
    if any(word in q for word in ("total", "sum")):
        return f'SELECT SUM("{metric}") AS total_{metric} FROM "{table_name}"'
    if any(word in q for word in ("top", "highest", "max", "largest")):
        return f'SELECT * FROM "{table_name}" ORDER BY "{metric}" DESC LIMIT 10'
    terms = [term for term in re.findall(r"[a-zA-Z0-9_/-]+", question) if len(term) > 3]
    for term in terms:
        if term.lower() in {"which", "what", "where", "when", "who", "is", "the", "show", "list", "team", "owns", "owner", "product", "endpoint"}:
            continue
        safe_term = term.replace("'", "")
        like_clauses = " OR ".join(f"""CAST("{column}" AS TEXT) LIKE '%{safe_term}%'""" for column in columns)
        if like_clauses:
            return f'SELECT * FROM "{table_name}" WHERE {like_clauses} LIMIT 20'
    return f'SELECT * FROM "{table_name}" LIMIT 20'


def execute_sql(db_path: Path, sql: str) -> list[dict[str, Any]]:
    if not is_read_only_sql(sql):
        raise ValueError("Only read-only SELECT queries are allowed")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql).fetchmany(100)
    return [dict(row) for row in rows]


def summarize_rows(question: str, sql: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "I checked the structured data, but it did not return any matching rows."
    if len(rows) == 1 and len(rows[0]) == 1:
        key, value = next(iter(rows[0].items()))
        return f"The answer from the structured data is {value}."
    q = question.lower()
    first = rows[0]
    lower_keys = {key.lower(): key for key in first}
    if any(word in q for word in ("where", "venue", "location")):
        for key_name in ("venue", "location", "address"):
            if key_name in lower_keys:
                return f"The venue/location is {first[lower_keys[key_name]]}."
    if any(word in q for word in ("when", "date", "time")):
        for key_name in ("date", "time"):
            if key_name in lower_keys:
                return f"The date/time is {first[lower_keys[key_name]]}."
    if any(word in q for word in ("owner", "owns", "team")):
        for key_name in ("owner_team", "owner", "team"):
            if key_name in lower_keys:
                return f"The owner/team is {first[lower_keys[key_name]]}."
    preview = rows[:5]
    return f"I found {len(rows)} matching structured row(s). Top result: {preview[0]}"
