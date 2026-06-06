from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.models.schemas import IngestedChunk, Source


def chunk_text(text: str, max_chars: int = 1400, overlap: int = 160) -> list[str]:
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        window = text[start:end]
        split_at = max(window.rfind("\n"), window.rfind(". "))
        if split_at > max_chars * 0.55 and end < len(text):
            end = start + split_at + 1
            window = text[start:end]
        chunks.append(window.strip())
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def chunks_from_text(
    *,
    dataset_id: str,
    input_id: str,
    text: str,
    title: str,
    file_name: str | None = None,
    url: str | None = None,
    metadata: dict | None = None,
) -> list[IngestedChunk]:
    output: list[IngestedChunk] = []
    for idx, chunk in enumerate(chunk_text(text)):
        source = Source(
            id=f"{input_id}:{idx}",
            title=title,
            file_name=file_name,
            url=url,
            text=chunk,
        )
        output.append(
            IngestedChunk(
                id=str(uuid4()),
                dataset_id=dataset_id,
                input_id=input_id,
                text=chunk,
                source=source,
                metadata=metadata or {},
            )
        )
    return output


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")
