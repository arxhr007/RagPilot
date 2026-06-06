# RAGX

RAGX is a hackathon-ready Adaptive Multi-RAG Orchestrator. It accepts mixed inputs, analyzes their structure, selects the best retrieval path, and answers questions with route explanations, citations, generated SQL, and a lightweight graph view.

This is intentionally not a "chat with PDFs" clone. RAGX composes reusable retrieval modules:

- Semantic RAG for PDFs, DOCX, Markdown, text, and website content.
- SQL RAG for CSV/XLSX analytical questions.
- Graph-style inspection for entity-heavy or relationship-style data.
- Hybrid routing when a dataset mixes documents, tables, and websites.

## Quick Start

Backend:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:OPENAI_API_KEY="your_key_here"
uvicorn app.main:app --reload
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

RAGX can run without `OPENAI_API_KEY` for local smoke tests by using deterministic lexical retrieval and SQL heuristics. For the strongest demo, set the key.

## Demo Flow

1. Upload `examples/demo_notes.md` and `examples/sales.csv`.
2. Ask: `What is RAGX designed to do?`
3. Ask: `What is the total revenue?`
4. Ask: `What relationships exist between RAGX, SQL RAG, and Semantic RAG?`
5. Ingest a small website URL with max pages set to `1` or `2`.

The UI shows selected route, confidence, reasoning, source citations, generated SQL, result rows, and extracted graph entities.

For the adaptive text demo, upload `examples/mixed_college_data.txt`. RAGX will segment the text, convert reliable table-like sections into SQLite tables, activate keyword lookup for person/name queries, activate graph retrieval for relationship questions, and show the selected RAG modes in the dashboard.

The universal answering path also includes query normalization, extracted role/contact/event facts, reranked evidence, and answer validation. Try `who is the princiapl?`, `who is the CEO?`, `where is the event venue?`, and `which team owns the invoice endpoint?` against the fixtures in `examples/`.

## Environment Variables

- `OPENAI_API_KEY`: enables OpenAI chat and embeddings.
- `OPENAI_CHAT_MODEL`: defaults to `gpt-4o-mini`.
- `OPENAI_EMBEDDING_MODEL`: defaults to `text-embedding-3-small`.
- `RAGX_DATA_DIR`: optional local storage directory; defaults to `backend/data`.

## Repository Layout

```text
backend/app/
  api/             FastAPI endpoints
  ingestion/       files, tables, and refactored web scraper adapter
  analysis/        dataset intelligence and architecture selection
  orchestration/   LangGraph-backed deterministic flows
  rag/             semantic, SQL, and graph modules
frontend/src/      React dashboard
docs/              setup, demo, architecture, submission notes
examples/          demo files
```

See `docs/` for the fuller hackathon submission notes.
