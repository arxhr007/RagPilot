from pathlib import Path

import pandas as pd

from app.analysis.analyzer import analyze_dataset
from app.analysis.rag_classifier import classify_segments_for_rag
from app.analysis.segmenter import segment_text
from app.ingestion.files import detect_file_kind
from app.ingestion.table_extract import load_text_tables
from app.orchestration.router import classify_query
from app.orchestration.query import understand_query
from app.analysis.facts import extract_facts_from_segments
from fastapi.testclient import TestClient
from app.main import app
from app.rag.sql import execute_sql, generate_sql, is_read_only_sql, load_dataframe
from app.store import Dataset, TableInfo


def test_detect_file_kind():
    assert detect_file_kind(Path("report.pdf")) == "pdf"
    assert detect_file_kind(Path("notes.md")) == "text"
    assert detect_file_kind(Path("sales.csv")) == "table"
    assert detect_file_kind(Path("workbook.xlsx")) == "table"


def test_sql_guardrails():
    assert is_read_only_sql("SELECT * FROM table_abc")
    assert not is_read_only_sql("DROP TABLE table_abc")
    assert not is_read_only_sql("DELETE FROM table_abc")


def test_sql_execution(tmp_path):
    db_path = tmp_path / "demo.db"
    df = pd.DataFrame({"region": ["North", "South"], "revenue": [10, 20]})
    load_dataframe(df, db_path, "sales")
    sql = generate_sql("what is the total revenue?", "sales", ["region", "revenue"])
    rows = execute_sql(db_path, sql)
    assert rows
    assert list(rows[0].values())[0] == 30


def test_query_classifier_routes_sql_when_table_available(tmp_path):
    dataset = Dataset(id="d1", name="demo")
    dataset.tables.append(
        TableInfo(
            input_id="i1",
            table_name="sales",
            db_path=tmp_path / "demo.db",
            columns=["region", "revenue"],
            row_count=2,
            source_name="sales.csv",
        )
    )
    route, confidence, reason = classify_query(dataset, "what is the total revenue?")
    assert route == "sql"
    assert confidence > 0.8
    assert "structured" in reason.lower()


def test_dataset_analysis_selects_hybrid_when_text_and_tables(tmp_path):
    dataset = Dataset(id="d1", name="demo")
    dataset.inputs = [{"id": "i1", "kind": "text"}, {"id": "i2", "kind": "table"}]
    dataset.chunks = [object()]  # analyzer only checks truthiness
    dataset.tables.append(
        TableInfo(
            input_id="i2",
            table_name="sales",
            db_path=tmp_path / "demo.db",
            columns=["region", "revenue"],
            row_count=2,
            source_name="sales.csv",
        )
    )
    analysis = analyze_dataset(dataset)
    assert analysis.selected_strategy == "hybrid"
    assert analysis.characteristics["has_tables"] is True


def test_segmenter_detects_text_table_and_keyword_sections():
    text = Path("examples/mixed_college_data.txt").read_text(encoding="utf-8")
    segments = segment_text(text, "mixed_college_data.txt", "input1")
    assert any(segment.rag_module == "sql" for segment in segments)
    assert any(segment.rag_module in {"keyword", "graph", "hierarchical"} for segment in segments)


def test_text_derived_table_loads_to_sql(tmp_path, monkeypatch):
    import app.ingestion.table_extract as table_extract

    monkeypatch.setattr(table_extract, "SQLITE_DIR", tmp_path)
    text = Path("examples/mixed_college_data.txt").read_text(encoding="utf-8")
    segments = segment_text(text, "mixed_college_data.txt", "input1")
    tables = load_text_tables("dataset1", "mixed_college_data.txt", segments)
    assert tables
    sql = generate_sql("how many departments are listed?", tables[0].table_name, tables[0].columns)
    rows = execute_sql(tables[0].db_path, sql)
    assert rows
    assert list(rows[0].values())[0] >= 3


def test_person_lookup_routes_to_keyword_when_text_available():
    dataset = Dataset(id="d2", name="college")
    dataset.chunks = [object()]
    route, confidence, reason = classify_query(dataset, "who is Aaron Thomas?")
    assert route == "keyword"
    assert confidence > 0.8
    assert "keyword" in reason.lower()


def test_route_override_wins(tmp_path):
    dataset = Dataset(id="d3", name="college")
    route, confidence, reason = classify_query(dataset, "who is Aaron Thomas?", "graph")
    assert route == "graph"
    assert confidence == 1.0
    assert "override" in reason.lower()


def test_fact_extraction_finds_universal_roles_and_events():
    company = segment_text(Path("examples/company_data.txt").read_text(encoding="utf-8"), "company_data.txt", "company")
    event = segment_text(Path("examples/event_data.txt").read_text(encoding="utf-8"), "event_data.txt", "event")
    facts = extract_facts_from_segments(company + event)
    assert any(f.subject == "ceo" and "Maya Raman" in f.object for f in facts)
    assert any(f.subject == "venue" and "Meridian" in f.object for f in facts)
    assert any(f.subject == "date" and "2026" in f.object for f in facts)


def test_query_understanding_normalizes_typo():
    understood = understand_query("who is the princiapl?")
    assert "principal" in understood.normalized.lower()
    assert understood.intent == "point_lookup"


def _upload_fixture(path: str):
    client = TestClient(app)
    with open(path, "rb") as handle:
        body = client.post("/api/upload", files=[("files", (Path(path).name, handle, "text/plain"))]).json()
    return client, body["dataset_id"]


def test_api_answers_principal_and_ceo_from_facts():
    client, dataset_id = _upload_fixture("examples/mixed_college_data.txt")
    answer = client.post("/api/chat", json={"dataset_id": dataset_id, "question": "who is the princiapl?"}).json()
    assert answer["answer_validation"]["status"] == "grounded"
    assert "Dr. Paul Thomas" in answer["answer"]

    client, dataset_id = _upload_fixture("examples/company_data.txt")
    answer = client.post("/api/chat", json={"dataset_id": dataset_id, "question": "who is the CEO?"}).json()
    assert answer["answer_validation"]["status"] == "grounded"
    assert "Maya Raman" in answer["answer"]


def test_api_rejects_fake_hod_message_and_answers_real_hod():
    client, dataset_id = _upload_fixture("examples/mixed_college_data.txt")
    answer = client.post("/api/chat", json={"dataset_id": dataset_id, "question": "who is the hod of cse?"}).json()
    assert answer["answer_validation"]["status"] == "grounded"
    assert "Neena George" in answer["answer"]
    assert "Message About Computer Science" not in answer["answer"]


def test_api_answers_event_venue_and_product_owner():
    client, dataset_id = _upload_fixture("examples/event_data.txt")
    answer = client.post("/api/chat", json={"dataset_id": dataset_id, "question": "where is the event venue?"}).json()
    assert answer["answer_validation"]["status"] == "grounded"
    assert "Meridian Convention Center" in answer["answer"]

    client, dataset_id = _upload_fixture("examples/product_docs.txt")
    answer = client.post("/api/chat", json={"dataset_id": dataset_id, "question": "which team owns the invoice endpoint?"}).json()
    assert answer["answer_validation"]["status"] == "grounded"
    assert "Billing Team" in answer["answer"]


def test_api_universal_demo_uses_natural_answers():
    client, dataset_id = _upload_fixture("examples/universal_all_rag_demo.txt")
    ceo = client.post("/api/chat", json={"dataset_id": dataset_id, "question": "who is the CEO?"}).json()
    assert ceo["answer_validation"]["status"] == "grounded"
    assert "Maya Iyer" in ceo["answer"]
    assert "Scope/context" not in ceo["answer"]

    products = client.post("/api/chat", json={"dataset_id": dataset_id, "question": "how many products are listed?"}).json()
    assert products["answer_validation"]["status"] == "grounded"
    assert "structured data" in products["answer"].lower() or "answer" in products["answer"].lower()


def test_relationship_question_uses_graph_not_sql_for_connected_products():
    client, dataset_id = _upload_fixture("examples/universal_all_rag_demo.txt")
    answer = client.post("/api/chat", json={"dataset_id": dataset_id, "question": "which products are connected to BeaconAI?"}).json()
    assert answer["route"] in {"graph", "hybrid"}
    assert "graph" in answer["retrievers_used"]


def test_point_lookup_without_confirmed_fact_is_not_raw_dump():
    client, dataset_id = _upload_fixture("examples/universal_all_rag_demo.txt")
    answer = client.post("/api/chat", json={"dataset_id": dataset_id, "question": "who is the chief wizard?"}).json()
    assert "=== URL" not in answer["answer"]
    assert "I could not find" in answer["answer"]


def test_casual_chat_skips_retrieval():
    client, dataset_id = _upload_fixture("examples/universal_all_rag_demo.txt")
    answer = client.post("/api/chat", json={"dataset_id": dataset_id, "question": "hi"}).json()
    assert answer["query_intent"] == "casual_chat"
    assert answer["answer_validation"]["status"] == "casual_chat"
    assert answer["candidate_count"] == 0
    assert "uploaded data" in answer["answer"]


def test_big_universal_fixture_exercises_all_rag_modes():
    text = Path("examples/big_universal_ragx_test_data.txt").read_text(encoding="utf-8")
    segments = classify_segments_for_rag(segment_text(text, "big_universal_ragx_test_data.txt", "big"), use_openai=False)
    modes = {segment.rag_module for segment in segments}
    assert {"semantic", "sql", "graph", "keyword", "hierarchical"}.issubset(modes)
    assert all(segment.metadata.get("primary_rag") == segment.rag_module for segment in segments)
    assert all(segment.metadata.get("classifier") == "heuristic" for segment in segments)


def test_big_universal_fixture_loads_reliable_text_tables_only(tmp_path, monkeypatch):
    import app.ingestion.table_extract as table_extract

    monkeypatch.setattr(table_extract, "SQLITE_DIR", tmp_path)
    text = Path("examples/big_universal_ragx_test_data.txt").read_text(encoding="utf-8")
    segments = classify_segments_for_rag(segment_text(text, "big_universal_ragx_test_data.txt", "big"), use_openai=False)
    tables = load_text_tables("big_dataset", "big_universal_ragx_test_data.txt", segments)
    names = " ".join(table.source_name for table in tables)
    assert len(tables) >= 5
    assert all(table.row_count >= 2 for table in tables)
    assert "big_universal" in names


def test_rag_classifier_falls_back_when_ai_unavailable(monkeypatch):
    import app.analysis.rag_classifier as rag_classifier

    monkeypatch.setattr(rag_classifier, "_classify_with_openai", lambda segments: {})
    text = "Overview\nThis narrative explains a product strategy without a table."
    segments = rag_classifier.classify_segments_for_rag(segment_text(text, "demo.txt", "demo"), use_openai=True)
    assert segments[0].metadata["classifier"] == "heuristic"
    assert segments[0].metadata["primary_rag"] == segments[0].rag_module


def test_upload_response_includes_rag_classification_metadata(monkeypatch):
    import app.analysis.rag_classifier as rag_classifier

    monkeypatch.setattr(rag_classifier, "OPENAI_API_KEY", "")
    client, dataset_id = _upload_fixture("examples/big_universal_ragx_test_data.txt")
    analysis = client.get(f"/api/datasets/{dataset_id}/analysis").json()
    assignments = analysis["method_assignments"]
    assert assignments
    assert analysis["rag_classification_summary"]["counts"]["sql"] >= 1
    assert any(item["classifier"] == "heuristic" for item in assignments)
    assert all("primary_rag" in item and "secondary_rags" in item and "signals" in item for item in assignments)


def test_web_ingestion_recursively_crawls_same_domain(monkeypatch):
    import app.ingestion.web as web

    pages = {
        "https://example.test/": '<html><head><title>Home</title></head><body>Home page text <a href="/about">About</a></body></html>',
        "https://example.test/about": '<html><head><title>About</title></head><body>About page text <a href="/team">Team</a></body></html>',
        "https://example.test/team": "<html><head><title>Team</title></head><body>Team page text</body></html>",
    }

    monkeypatch.setattr(web, "_sitemap_urls", lambda *args, **kwargs: [])
    monkeypatch.setattr(web, "_fetch_requests", lambda url, session: pages[url])
    record, chunks = web.ingest_url(dataset_id="web1", url="https://example.test", max_pages=3)
    urls = {chunk.source.url for chunk in chunks}
    assert record["recursive"] is True
    assert record["pages"] == 3
    assert "https://example.test/about" in urls
    assert "https://example.test/team" in urls


def test_web_ingestion_uses_playwright_when_requested(monkeypatch):
    import app.ingestion.web as web

    called = {"playwright": False}

    monkeypatch.setattr(web, "_sitemap_urls", lambda *args, **kwargs: [])

    def fake_playwright(url):
        called["playwright"] = True
        return "<html><head><title>JS Page</title></head><body>Rendered JavaScript content</body></html>"

    monkeypatch.setattr(web, "_fetch_playwright", fake_playwright)
    record, chunks = web.ingest_url(dataset_id="web2", url="https://example.test", max_pages=1, use_playwright=True)
    assert called["playwright"] is True
    assert record["use_playwright"] is True
    assert chunks
