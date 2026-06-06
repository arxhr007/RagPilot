# Demo Script

## Goal

Show that RAGX automatically selects retrieval architecture for heterogeneous data.

## Steps

1. Start backend and frontend.
2. Upload `examples/demo_notes.md` and `examples/sales.csv`.
3. Point out the Dataset Intelligence panel:
   - `has_tables: true`
   - `has_unstructured_text: true`
   - selected strategy: `HYBRID`
4. Ask: `What is RAGX designed to do?`
   - Expected route: Semantic.
   - Expected UI: citation in Sources.
5. Ask: `What is the total revenue?`
   - Expected route: SQL.
   - Expected UI: generated SQLite query and result rows.
6. Ask: `What relationships exist between RAGX, SQL RAG, and Semantic RAG?`
   - Expected route: Graph.
   - Expected UI: graph entities and semantic fallback answer.
7. Ingest a URL with max pages set to `1`.
   - Expected UI: website content appears as semantic input with source URLs.

## Screenshot Placeholders

- Upload and dataset intelligence panel.
- Selected architecture and workflow nodes.
- SQL RAG answer with generated SQL.
- Semantic RAG answer with citations.
- Graph entity display.
