# RAGPilot Architecture

RAGPilot composes retrieval modules from dataset characteristics instead of generating a codebase dynamically.

## Dataset Flow

```mermaid
flowchart LR
  A["Input files / URL"] --> B["analyze_dataset"]
  B --> C["segment_dataset"]
  C --> D["select_strategy"]
  D --> E["build_pipeline"]
```

## Query Flow

```mermaid
flowchart LR
  Q["Question"] --> C["classify_query"]
  C --> R["route_query"]
  R --> S["semantic_rag"]
  R --> T["sql_rag"]
  R --> G["graph_layer"]
  S --> A["synthesize_answer"]
  T --> A
  G --> A
```

## Modules

- Semantic RAG chunks unstructured content, indexes it in ChromaDB when OpenAI is configured, and falls back to local lexical retrieval for demos/tests.
- SQL RAG loads CSV/XLSX files into SQLite, generates read-only SQL, executes it, and returns the query plus rows.
- Graph layer extracts entity co-occurrences and exposes graph JSON for visualization.
- Router sends aggregation questions to SQL, factual questions to semantic retrieval, relationship questions to graph, and mixed questions to hybrid synthesis.

## Web Ingestion

`backend/app/ingestion/web.py` is the source of truth for recursive website ingestion. The root `scraper.py` file is only a small CLI wrapper around that module for standalone crawler testing.
