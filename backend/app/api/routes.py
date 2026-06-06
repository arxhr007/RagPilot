from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import UPLOAD_DIR
from app.analysis.rag_classifier import classify_segments_for_rag
from app.analysis.segmenter import segment_table_input
from app.analysis.facts import extract_facts_from_segments
from app.ingestion.files import detect_file_kind, ingest_document_file, ingest_table_file, make_input_record
from app.ingestion.table_extract import load_text_tables
from app.ingestion.web import ingest_url
from app.models.schemas import ChatRequest, ChatResponse, UrlIngestRequest
from app.orchestration.graphs import run_dataset_graph, run_query_graph
from app.rag.graph import build_graph
from app.rag.hierarchical import hierarchical_index
from app.rag.keyword import keyword_index
from app.rag.semantic import semantic_index
from app.store import store

router = APIRouter(prefix="/api")


def _refresh(dataset_id: str):
    dataset = store.get(dataset_id)
    dataset.facts = extract_facts_from_segments(dataset.segments)
    dataset.graph = build_graph(dataset.chunks)
    if dataset.chunks:
        semantic_index.add(dataset.id, dataset.chunks)
        keyword_index.add(dataset.id, dataset.chunks)
    hierarchical_index.add(dataset.id, dataset.segments)
    return run_dataset_graph(dataset)


def _ingest_local_file(dataset, path: Path, display_name: str | None = None):
    kind = detect_file_kind(path)
    record = make_input_record(Path(display_name or path.name), kind)
    input_id = record["id"]
    dataset.inputs.append(record)
    if kind == "table":
        table = ingest_table_file(dataset.id, input_id, path)
        dataset.tables.append(table)
        dataset.segments.append(segment_table_input(display_name or path.name, input_id, table.table_name, table.columns, table.row_count))
    elif kind in {"pdf", "docx", "text"}:
        chunks, segments = ingest_document_file(dataset.id, input_id, path)
        dataset.segments.extend(segments)
        dataset.tables.extend(load_text_tables(dataset.id, display_name or path.name, segments))
        dataset.chunks.extend(chunks)
    else:
        record["warning"] = "Unsupported file type was stored but not indexed."


@router.post("/upload")
async def upload(files: list[UploadFile] = File(...)):
    dataset = store.create("Uploaded Dataset")
    for file in files:
        suffix = Path(file.filename or "upload.bin").suffix
        safe_name = f"{uuid4()}{suffix}"
        target = UPLOAD_DIR / safe_name
        content = await file.read()
        target.write_bytes(content)
        kind = detect_file_kind(target)
        record = make_input_record(Path(file.filename or safe_name), kind)
        input_id = record["id"]
        dataset.inputs.append(record)
        if kind == "table":
            table = ingest_table_file(dataset.id, input_id, target)
            dataset.tables.append(table)
            dataset.segments.append(segment_table_input(file.filename or safe_name, input_id, table.table_name, table.columns, table.row_count))
        elif kind in {"pdf", "docx", "text"}:
            chunks, segments = ingest_document_file(dataset.id, input_id, target)
            dataset.segments.extend(segments)
            dataset.tables.extend(load_text_tables(dataset.id, file.filename or safe_name, segments))
            dataset.chunks.extend(chunks)
        else:
            record["warning"] = "Unsupported file type was stored but not indexed."

    dataset = _refresh(dataset.id)
    return {
        "dataset_id": dataset.id,
        "analysis": dataset.analysis,
        "architecture": dataset.architecture,
    }


@router.post("/demo/universal")
async def demo_universal():
    demo_path = Path(__file__).resolve().parents[3] / "examples" / "universal_all_rag_demo.txt"
    if not demo_path.exists():
        raise HTTPException(status_code=404, detail="Universal demo dataset was not found.")
    dataset = store.create("Universal Multi-RAG Demo")
    _ingest_local_file(dataset, demo_path, "universal_all_rag_demo.txt")
    dataset = _refresh(dataset.id)
    return {
        "dataset_id": dataset.id,
        "analysis": dataset.analysis,
        "architecture": dataset.architecture,
    }


@router.post("/ingest/url")
async def ingest_website(payload: UrlIngestRequest):
    dataset = store.create("Website Dataset")
    try:
        record, chunks = ingest_url(
            dataset_id=dataset.id,
            url=payload.url,
            max_pages=payload.max_pages,
            use_playwright=payload.use_playwright,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    dataset.inputs.append(record)
    dataset.chunks.extend(chunks)
    from app.analysis.segmenter import segment_text
    from app.ingestion.table_extract import load_text_tables

    combined = "\n\n".join(chunk.text for chunk in chunks)
    segments = classify_segments_for_rag(segment_text(combined, record["name"], record["id"]))
    dataset.segments.extend(segments)
    dataset.tables.extend(load_text_tables(dataset.id, record["name"], segments))
    dataset = _refresh(dataset.id)
    return {
        "dataset_id": dataset.id,
        "analysis": dataset.analysis,
        "architecture": dataset.architecture,
    }


@router.get("/datasets/{dataset_id}/analysis")
async def analysis(dataset_id: str):
    dataset = _refresh(dataset_id)
    return dataset.analysis


@router.get("/datasets/{dataset_id}/architecture")
async def architecture(dataset_id: str):
    dataset = _refresh(dataset_id)
    return dataset.architecture


@router.get("/datasets/{dataset_id}/graph")
async def graph(dataset_id: str):
    return store.get(dataset_id).graph


@router.get("/datasets/{dataset_id}/segments")
async def segments(dataset_id: str):
    return store.get(dataset_id).segments


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    dataset = store.get(payload.dataset_id)
    return run_query_graph(dataset, payload.question, payload.route_override)
