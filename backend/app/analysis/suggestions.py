from __future__ import annotations

import json
import os
from typing import Any

from app.config import OPENAI_API_KEY, OPENAI_CHAT_MODEL
from app.store import Dataset


def _fallback_questions(dataset: Dataset) -> list[str]:
    questions: list[str] = []
    columns = " ".join(" ".join(table.columns) for table in dataset.tables).lower()
    table_names = " ".join(table.source_name for table in dataset.tables).lower()
    graph_nodes = dataset.graph.get("nodes", [])
    segment_titles = [segment.title for segment in dataset.segments if segment.title]

    if any(term in columns for term in ("ceo", "cto", "head", "owner", "contact")):
        questions.append("Who are the key people or role owners in this data?")
    if "product" in columns:
        questions.append("How many active products are listed?")
    if "speaker" in columns or "event" in table_names:
        questions.append("List the event speakers.")
    if "venue" in columns:
        questions.append("Where are the event venues?")
    if "endpoint" in columns:
        questions.append("Which API endpoints are listed?")
    if graph_nodes:
        label = str(graph_nodes[0].get("label") or graph_nodes[0].get("id"))
        questions.append(f"Which systems or entities are connected to {label}?")
    if any(segment.rag_module == "keyword" for segment in dataset.segments):
        questions.append("What exact contacts, IDs, codes, or policy numbers are listed?")
    if any(segment.rag_module == "hierarchical" for segment in dataset.segments):
        questions.append("Summarize the longest policy or handbook section.")
    if segment_titles:
        questions.append(f"What are the main points in the {segment_titles[0]} section?")

    return list(dict.fromkeys(questions))[:6]


def _profile(dataset: Dataset) -> dict[str, Any]:
    return {
        "inputs": [{"name": item.get("name"), "kind": item.get("kind")} for item in dataset.inputs[:6]],
        "tables": [
            {"source": table.source_name, "columns": table.columns, "rows": table.row_count}
            for table in dataset.tables[:8]
        ],
        "segments": [
            {
                "title": segment.title,
                "rag": segment.rag_module,
                "preview": segment.text_preview[:260],
            }
            for segment in dataset.segments[:12]
        ],
        "entities": [
            {"label": node.get("label"), "type": node.get("type")}
            for node in dataset.graph.get("nodes", [])[:12]
        ],
    }


def _openai_questions(dataset: Dataset) -> list[str]:
    if not OPENAI_API_KEY or os.getenv("PYTEST_CURRENT_TEST"):
        return []
    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY, timeout=8.0)
        response = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Generate useful custom user questions for a RAG app from the dataset profile. "
                        "Questions must be answerable from the uploaded data, specific to visible entities/columns/sections, "
                        "and should cover semantic, SQL, graph, keyword, hierarchical, or hybrid retrieval when available. "
                        "Return JSON: {\"questions\": [\"...\"]}. Return 4 to 6 questions."
                    ),
                },
                {"role": "user", "content": json.dumps(_profile(dataset), ensure_ascii=True)},
            ],
        )
        data = json.loads(response.choices[0].message.content or "{}")
    except Exception:
        return []
    questions = data.get("questions", [])
    if not isinstance(questions, list):
        return []
    clean = [str(question).strip() for question in questions if str(question).strip().endswith("?")]
    return list(dict.fromkeys(clean))[:6]


def generate_question_suggestions(dataset: Dataset) -> tuple[list[str], str]:
    questions = _openai_questions(dataset)
    if questions:
        return questions, "openai"
    return _fallback_questions(dataset), "heuristic_fallback"
