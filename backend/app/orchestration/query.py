from __future__ import annotations

import re
from dataclasses import dataclass


TYPO_MAP = {
    "princiapl": "principal",
    "collage": "college",
    "sahrdaya": "sahrdaya",
    "ceo": "CEO",
    "cto": "CTO",
}


@dataclass
class QueryUnderstanding:
    original: str
    normalized: str
    expanded: str
    intent: str
    target: str
    role_target: str = ""
    qualifier: str = ""


CASUAL_CHAT_RE = re.compile(
    r"^\s*(hi|hello|hey|yo|sup|thanks|thank you|ok|okay|cool|nice|good morning|good evening|good afternoon|bye|goodbye)[!?.\s]*$",
    re.I,
)


def normalize_query(question: str) -> str:
    normalized = re.sub(r"\s+", " ", question.strip())
    for wrong, right in TYPO_MAP.items():
        normalized = re.sub(rf"\b{wrong}\b", right, normalized, flags=re.I)
    return normalized


def understand_query(question: str, vocabulary: list[str] | None = None) -> QueryUnderstanding:
    normalized = normalize_query(question)
    lower = normalized.lower()
    intent = "factual"
    if CASUAL_CHAT_RE.match(normalized):
        return QueryUnderstanding(question, normalized, normalized, "casual_chat", "", "", "")
    if re.search(r"\b(who is|who's|current|principal|ceo|cto|founder|hod|head|chairman|director|manager|speaker|organizer)\b", lower):
        intent = "point_lookup"
    if re.search(r"\b(list|all|show all|which|speakers|people|members|departments|products|events)\b", lower):
        intent = "list"
    if re.search(r"\b(how many|count|total|sum|average|avg|maximum|minimum)\b", lower):
        intent = "aggregate"
    if re.search(r"\b(where|venue|location|address)\b", lower):
        intent = "location"
    if re.search(r"\b(when|date|time|schedule)\b", lower):
        intent = "time"
    if re.search(r"\b(related|relationship|connected|depends|owns|associated|works on)\b", lower):
        intent = "relationship"
    if re.search(r"\b(compare|difference|versus|vs)\b", lower):
        intent = "comparison"

    expansions = [normalized]
    role_expansions = {
        "principal": "administrator leadership head",
        "ceo": "chief executive officer founder leadership",
        "cto": "chief technology officer technology head",
        "hod": "head of department",
        "venue": "location address place",
        "speaker": "presenter guest",
    }
    for term, expansion in role_expansions.items():
        if re.search(rf"\b{term}\b", lower):
            expansions.append(expansion)
    if vocabulary:
        lower_vocab = [item for item in vocabulary if item.lower() in lower]
        expansions.extend(lower_vocab[:8])

    target = _target_from_query(normalized)
    role_target, qualifier = _role_and_qualifier(normalized)
    return QueryUnderstanding(question, normalized, " ".join(dict.fromkeys(" ".join(expansions).split())), intent, target, role_target, qualifier)


def _target_from_query(query: str) -> str:
    lower = query.lower()
    role_match = re.search(r"\b(?:who is|who's|current|list all|list|where is|when is|what is)\s+(?:the\s+)?([a-zA-Z0-9 &/-]{2,50})", lower)
    if role_match:
        return role_match.group(1).strip(" ?.")
    for term in ("principal", "ceo", "cto", "venue", "speaker", "organizer", "chairman", "hod", "head of department"):
        if term in lower:
            return term
    return ""


def _role_and_qualifier(query: str) -> tuple[str, str]:
    lower = query.lower()
    role_aliases = {
        "hod": "head of department",
        "head of department": "head of department",
        "principal": "principal",
        "ceo": "ceo",
        "cto": "cto",
        "chairman": "chairman",
        "director": "director",
        "manager": "manager",
        "speaker": "speaker",
        "organizer": "organizer",
    }
    role_target = ""
    for alias, canonical in role_aliases.items():
        if re.search(rf"\b{re.escape(alias)}\b", lower):
            role_target = canonical
            break
    qualifier = ""
    match = re.search(r"\b(?:of|for|in)\s+([a-zA-Z0-9 &/-]{2,40})", lower)
    if match:
        qualifier = match.group(1).strip(" ?.")
    return role_target, qualifier
