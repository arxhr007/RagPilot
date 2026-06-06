from __future__ import annotations

import re
from collections import Counter, defaultdict

from app.models.schemas import IngestedChunk


ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3}\b")


def _entity_type(name: str) -> str:
    lower = name.lower()
    if any(word in lower for word in ("department", "engineering", "science", "biotechnology", "electronics", "computer")):
        return "Department"
    if any(word in lower for word in ("b.tech", "m.tech", "ph.d", "program", "course")):
        return "Program"
    if any(word in lower for word in ("committee", "cell", "council", "body", "iqac")):
        return "Committee"
    if any(word in lower for word in ("pdf", "doc", "report", "form", "calendar", "handbook")):
        return "Document"
    if any(word in lower for word in ("prof", "dr", "mr", "mrs", "ms", "thomas")) or len(name.split()) in (2, 3):
        return "Person"
    return "Entity"


def build_graph(chunks: list[IngestedChunk], max_nodes: int = 30) -> dict:
    counts: Counter[str] = Counter()
    cooccurrence: defaultdict[tuple[str, str], int] = defaultdict(int)
    for chunk in chunks:
        entities = sorted({e.strip() for e in ENTITY_RE.findall(chunk.text) if len(e.strip()) > 2})
        counts.update(entities)
        for idx, left in enumerate(entities[:10]):
            for right in entities[idx + 1 : 10]:
                cooccurrence[(left, right)] += 1

    top = {name for name, _ in counts.most_common(max_nodes)}
    nodes = [{"id": name, "label": name, "type": _entity_type(name), "weight": counts[name]} for name in top]
    edges = [
        {"source": a, "target": b, "weight": weight, "label": "co-occurs"}
        for (a, b), weight in sorted(cooccurrence.items(), key=lambda item: item[1], reverse=True)
        if a in top and b in top
    ][:60]
    entity_types: Counter[str] = Counter(node["type"] for node in nodes)
    return {"nodes": nodes, "edges": edges, "entity_types": dict(entity_types)}


def graph_hint(question: str, graph: dict) -> str:
    nodes = graph.get("nodes", [])[:8]
    if not nodes:
        return "No strong entity relationships were extracted yet."
    names = ", ".join(node["label"] for node in nodes)
    return f"The lightweight graph layer found these prominent entities for relationship-style reasoning: {names}."
