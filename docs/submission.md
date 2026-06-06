# Hackathon Submission Notes

## Product Positioning

RAGX is an autonomous retrieval architecture orchestrator for heterogeneous enterprise knowledge.

## What Works

- File upload for PDF, DOCX, CSV, XLSX, Markdown, and text.
- URL ingestion through the existing scraper implementation.
- Dataset intelligence with strategy selection and confidence.
- Semantic RAG with citations.
- SQL RAG with SQLite execution and generated SQL display.
- Query routing across semantic, SQL, graph, and hybrid paths.
- Lightweight graph extraction and visualization data.
- React dashboard for ingestion, analysis, architecture, chat, sources, SQL, and graph entities.

## Tradeoffs

- Graph retrieval is intentionally lightweight for the MVP.
- ChromaDB/OpenAI is used when configured; local lexical fallback keeps demos and tests reliable.
- Dataset state is in memory for hackathon simplicity. Uploaded files, SQLite DBs, and vectors persist locally.

## Judge-Friendly Run

Use the files in `examples/` first, then add a short website ingestion demo. This keeps the core routes fast and predictable.
