from __future__ import annotations

import json
from collections import Counter
from typing import Any

from app.config import OPENAI_API_KEY, OPENAI_CHAT_MODEL
from app.models.schemas import Segment


RAG_MODES = {"semantic", "sql", "graph", "keyword", "hierarchical"}


def _heuristic_secondary(segment: Segment) -> list[str]:
    text = f"{segment.title} {segment.text_preview} {segment.text}".lower()
    secondary: list[str] = []
    if segment.rag_module != "keyword" and any(term in text for term in ("id", "email", "phone", "sku", "code", "acronym", "contact")):
        secondary.append("keyword")
    if segment.rag_module != "graph" and any(term in text for term in ("depends", "connected", "owns", "owned by", "reports to", "partner", "vendor")):
        secondary.append("graph")
    if segment.rag_module != "hierarchical" and len(segment.text) > 1600:
        secondary.append("hierarchical")
    if segment.rag_module != "semantic" and any(term in text for term in ("overview", "summary", "policy", "description", "explains")):
        secondary.append("semantic")
    return secondary[:3]


def _heuristic_signals(segment: Segment) -> list[str]:
    signals = [segment.segment_type]
    text = segment.text.lower()
    if "|" in segment.text or "," in segment.text:
        signals.append("structured delimiters")
    if any(term in text for term in ("email", "phone", "sku", "id", "code")):
        signals.append("exact identifiers")
    if any(term in text for term in ("depends", "connected", "owns", "partner", "vendor")):
        signals.append("relationship language")
    if len(segment.text) > 1600:
        signals.append("long section")
    return signals


def annotate_heuristic(segment: Segment) -> Segment:
    segment.metadata.update(
        {
            "classifier": segment.metadata.get("classifier", "heuristic"),
            "primary_rag": segment.rag_module,
            "secondary_rags": segment.metadata.get("secondary_rags", _heuristic_secondary(segment)),
            "signals": segment.metadata.get("signals", _heuristic_signals(segment)),
            "decision_reason": segment.metadata.get("decision_reason", " ".join(segment.reasons)),
        }
    )
    return segment


def _valid_mode(value: Any, fallback: str) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in RAG_MODES else fallback


def _valid_confidence(value: Any, fallback: float) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(0.0, min(0.98, confidence))


def _apply_ai_decision(segment: Segment, decision: dict[str, Any]) -> Segment:
    original_mode = segment.rag_module
    primary = _valid_mode(decision.get("primary_rag"), original_mode)
    sql_reliable = bool(decision.get("sql_candidate_is_reliable", False))

    if primary == "sql" and not (segment.segment_type == "sql_candidate" and segment.confidence >= 0.72 and sql_reliable):
        primary = original_mode
        reason_prefix = "SQL skipped because table structure was unreliable. "
    else:
        reason_prefix = ""

    secondary = []
    for mode in decision.get("secondary_rags", []) or []:
        valid = _valid_mode(mode, "")
        if valid and valid != primary and valid not in secondary:
            secondary.append(valid)

    confidence = _valid_confidence(decision.get("confidence"), segment.confidence)
    reason = str(decision.get("reason") or "OpenAI refined this segment's RAG method from structure and content signals.").strip()
    signals = [str(signal) for signal in (decision.get("signals") or []) if str(signal).strip()]

    segment.rag_module = primary  # type: ignore[assignment]
    segment.confidence = round(confidence, 2)
    segment.reasons = [reason_prefix + reason]
    segment.metadata.update(
        {
            "classifier": "openai",
            "primary_rag": primary,
            "secondary_rags": secondary[:3] or _heuristic_secondary(segment),
            "signals": signals[:6] or _heuristic_signals(segment),
            "decision_reason": reason_prefix + reason,
            "heuristic_rag": original_mode,
        }
    )
    return segment


def _classify_with_openai(segments: list[Segment]) -> dict[str, dict[str, Any]]:
    if not OPENAI_API_KEY or not segments:
        return {}
    payload = [
        {
            "id": segment.id,
            "title": segment.title,
            "heuristic_rag": segment.rag_module,
            "segment_type": segment.segment_type,
            "confidence": segment.confidence,
            "reasons": segment.reasons,
            "preview": segment.text_preview[:700],
        }
        for segment in segments[:24]
    ]
    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY, timeout=8.0)
        response = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify document segments for a universal Multi-RAG app. "
                        "Return JSON with key 'segments', an array of decisions. "
                        "Allowed primary_rag values: semantic, sql, graph, keyword, hierarchical. "
                        "Use sql only for reliable repeated records or delimited tables. "
                        "Use graph for relationships/entities, keyword for exact IDs/names/acronyms, "
                        "hierarchical for long parent sections, semantic for narrative meaning."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({"segments": payload}, ensure_ascii=True),
                },
            ],
        )
        data = json.loads(response.choices[0].message.content or "{}")
    except Exception:
        return {}
    decisions = data.get("segments", [])
    if not isinstance(decisions, list):
        return {}
    return {str(item.get("id")): item for item in decisions if isinstance(item, dict) and item.get("id")}


def classify_segments_for_rag(segments: list[Segment], use_openai: bool = True) -> list[Segment]:
    for segment in segments:
        annotate_heuristic(segment)
    decisions = _classify_with_openai(segments) if use_openai else {}
    if not decisions:
        for segment in segments:
            segment.metadata["classifier"] = "heuristic"
        return segments
    for segment in segments:
        decision = decisions.get(segment.id)
        if decision:
            _apply_ai_decision(segment, decision)
        else:
            segment.metadata["classifier"] = "ai_with_fallback"
    return segments


def classification_counts(segments: list[Segment]) -> dict[str, int]:
    counts = Counter(segment.rag_module for segment in segments)
    return {mode: counts.get(mode, 0) for mode in sorted(RAG_MODES)}
