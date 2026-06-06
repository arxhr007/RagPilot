import React, { useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, Database, FileUp, Globe, GitBranch, Loader2, MessageSquare, Route, Search } from "lucide-react";
import { chat, ingestUrl, uploadFiles } from "./services/api";
import type { Architecture, ChatResponse, DatasetAnalysis, RouteOverride } from "./types/ragx";
import "./styles.css";

function Panel({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="panel">
      <div className="panel-title">
        {icon}
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  );
}

function Confidence({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="confidence">
      <span>{pct}%</span>
      <div className="bar"><i style={{ width: `${pct}%` }} /></div>
    </div>
  );
}

export default function App() {
  const [datasetId, setDatasetId] = useState("");
  const [analysis, setAnalysis] = useState<DatasetAnalysis | null>(null);
  const [architecture, setArchitecture] = useState<Architecture | null>(null);
  const [answer, setAnswer] = useState<ChatResponse | null>(null);
  const [url, setUrl] = useState("");
  const [maxPages, setMaxPages] = useState(4);
  const [question, setQuestion] = useState("What are the most important facts in this dataset?");
  const [routeOverride, setRouteOverride] = useState<RouteOverride>("auto");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const activeNodes = useMemo(() => architecture?.workflow_nodes ?? analysis?.activated_nodes ?? [], [architecture, analysis]);

  async function run<T>(task: () => Promise<T>, onDone: (result: T) => void) {
    setBusy(true);
    setError("");
    try {
      const result = await task();
      onDone(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Adaptive Multi-RAG Orchestrator</p>
          <h1>RAGX</h1>
        </div>
        <div className="status">
          {datasetId ? `Dataset ${datasetId.slice(0, 8)}` : "No dataset loaded"}
        </div>
      </header>

      {error && <div className="error">{error}</div>}

      <div className="grid">
        <Panel title="Ingest" icon={<FileUp size={18} />}>
          <label className="drop">
            <input
              type="file"
              multiple
              accept=".pdf,.docx,.csv,.xlsx,.xls,.txt,.md,.markdown"
              onChange={(event) => {
                if (!event.target.files?.length) return;
                run(() => uploadFiles(event.target.files!), (res) => {
                  setDatasetId(res.dataset_id);
                  setAnalysis(res.analysis);
                  setArchitecture(res.architecture);
                  setAnswer(null);
                });
              }}
            />
            <FileUp size={22} />
            <span>Upload PDF, DOCX, CSV, XLSX, TXT, or MD</span>
          </label>
          <div className="url-row">
            <Globe size={18} />
            <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com" />
            <input
              className="pages"
              type="number"
              min={1}
              max={20}
              value={maxPages}
              onChange={(event) => setMaxPages(Number(event.target.value))}
              title="Max pages"
            />
            <button disabled={!url || busy} onClick={() => run(() => ingestUrl(url, maxPages), (res) => {
              setDatasetId(res.dataset_id);
              setAnalysis(res.analysis);
              setArchitecture(res.architecture);
              setAnswer(null);
            })}>
              {busy ? <Loader2 className="spin" size={16} /> : <Search size={16} />}
              Ingest
            </button>
          </div>
        </Panel>

        <Panel title="Dataset Intelligence" icon={<Activity size={18} />}>
          {analysis ? (
            <>
              <div className="strategy">
                <strong>{analysis.selected_strategy.toUpperCase()}</strong>
                <Confidence value={analysis.confidence} />
              </div>
              <div className="facts">
                {Object.entries(analysis.characteristics).map(([key, value]) => (
                  <span key={key}>{key.replaceAll("_", " ")}: <b>{String(value)}</b></span>
                ))}
              </div>
              <ul className="clean-list">
                {analysis.reasons.map((reason) => <li key={reason}>{reason}</li>)}
              </ul>
            </>
          ) : <p className="muted">Ingest data to see structure, modality, and routing signals.</p>}
        </Panel>

        <Panel title="RAG Modes" icon={<Route size={18} />}>
          {analysis ? (
            <>
              <div className="modules">
                {analysis.rag_modes_available.map((mode) => (
                  <span className={analysis.rag_modes_selected.includes(mode) ? "active-mode" : ""} key={mode}>
                    {mode}
                  </span>
                ))}
              </div>
              <p className="muted">{analysis.route_policy_summary}</p>
              {analysis.detected_tables.length > 0 && (
                <div className="table-list">
                  {analysis.detected_tables.map((table) => (
                    <article key={String(table.table_name)}>
                      <strong>{String(table.table_name)}</strong>
                      <p>{String(table.row_count)} rows · {Array.isArray(table.columns) ? table.columns.join(", ") : ""}</p>
                    </article>
                  ))}
                </div>
              )}
            </>
          ) : <p className="muted">Active RAG modes appear after ingestion.</p>}
        </Panel>

        <Panel title="Architecture" icon={<GitBranch size={18} />}>
          {architecture ? (
            <>
              <p className="architecture-name">{architecture.name}</p>
              <div className="modules">
                {architecture.modules.map((module) => (
                  <span key={String(module.name)}>{String(module.name)} · {String(module.status)}</span>
                ))}
              </div>
              <div className="workflow">
                {activeNodes.map((node) => <span key={node}>{node}</span>)}
              </div>
            </>
          ) : <p className="muted">RAGX will show the activated pipeline here.</p>}
        </Panel>

        <Panel title="Methods By Data" icon={<Activity size={18} />}>
          {analysis?.method_assignments?.length ? (
            <div className="method-list">
              {analysis.method_assignments.slice(0, 20).map((item, idx) => (
                <article key={`${String(item.title)}-${idx}`}>
                  <div className="segment-head">
                    <strong>{String(item.title)}</strong>
                    <span>{String(item.method)} · {Math.round(Number(item.confidence ?? 0) * 100)}%</span>
                  </div>
                  <p>{String(item.segment_type)} · {String(item.reason || "Selected from detected structure and query signals.")}</p>
                  {Boolean(item.table_name) && <small>SQLite table: {String(item.table_name)}</small>}
                </article>
              ))}
            </div>
          ) : <p className="muted">Upload data to see which RAG method is assigned to each section.</p>}
        </Panel>

        <Panel title="Ask" icon={<MessageSquare size={18} />}>
          <select className="route-select" value={routeOverride} onChange={(event) => setRouteOverride(event.target.value as RouteOverride)}>
            {["auto", "semantic", "sql", "graph", "keyword", "hierarchical", "hybrid"].map((mode) => (
              <option value={mode} key={mode}>{mode === "auto" ? "Auto route" : mode}</option>
            ))}
          </select>
          <div className="ask-row">
            <input value={question} onChange={(event) => setQuestion(event.target.value)} />
            <button disabled={!datasetId || !question || busy} onClick={() => run(() => chat(datasetId, question, routeOverride), setAnswer)}>
              {busy ? <Loader2 className="spin" size={16} /> : <Route size={16} />}
              Route
            </button>
          </div>
          {answer && (
            <div className="answer">
              <div className="route-line">
                <strong>{answer.route.toUpperCase()}</strong>
                <Confidence value={answer.confidence} />
              </div>
              <p className="muted">{answer.route_reason}</p>
              <div className="modules">
                {answer.retrievers_used.map((retriever) => <span className="active-mode" key={retriever}>{retriever}</span>)}
              </div>
              <div className={`validation ${answer.answer_validation?.status ?? "grounded"}`}>
                {(answer.answer_validation?.status ?? "grounded").replaceAll("_", " ")} · answer confidence {Math.round((answer.answer_confidence ?? 0) * 100)}%
              </div>
              <p className="final-answer">{answer.answer}</p>
              <p className="muted">Intent: {answer.query_intent} · normalized: {answer.normalized_query} · candidates: {answer.candidate_count}</p>
              {answer.fact_match && (
                <p className="muted">Fact match: {answer.fact_match.fact_type} · {answer.fact_match.subject} → {answer.fact_match.object}</p>
              )}
              {answer.retrievers_skipped.length > 0 && (
                <ul className="clean-list">
                  {answer.retrievers_skipped.map((item, idx) => (
                    <li key={idx}>{item.retriever}: {item.reason}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </Panel>

        <Panel title="Segments" icon={<Activity size={18} />}>
          {analysis?.segments?.length ? (
            <div className="segments">
              {analysis.segments.slice(0, 18).map((segment) => (
                <article key={segment.id}>
                  <div className="segment-head">
                    <strong>{segment.title}</strong>
                    <span>{segment.rag_module} · {Math.round(segment.confidence * 100)}%</span>
                  </div>
                  <p>{segment.text_preview}</p>
                  <small>{segment.reasons.join(" ")}</small>
                </article>
              ))}
            </div>
          ) : <p className="muted">RAGX will list detected sections and selected RAG modules here.</p>}
        </Panel>

        <Panel title="Sources" icon={<Search size={18} />}>
          {answer?.sources?.length ? (
            <div className="sources">
              {answer.sources.map((source, index) => (
                <article key={`${source.id}-${index}`}>
                  <strong>[{index + 1}] {source.title || source.file_name || source.url}</strong>
                  <p>{source.text.slice(0, 280)}</p>
                  {source.match_reason && <small>{source.match_reason}</small>}
                  {source.url && <a href={source.url} target="_blank" rel="noreferrer">{source.url}</a>}
                </article>
              ))}
            </div>
          ) : <p className="muted">Citations appear after semantic or hybrid answers.</p>}
        </Panel>

        <Panel title="SQL + Graph" icon={<Database size={18} />}>
          {answer?.generated_sql && <pre>{answer.generated_sql}</pre>}
          {answer?.sql_rows?.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>{Object.keys(answer.sql_rows[0]).map((key) => <th key={key}>{key}</th>)}</tr>
                </thead>
                <tbody>
                  {answer.sql_rows.slice(0, 8).map((row, idx) => (
                    <tr key={idx}>{Object.values(row).map((value, cell) => <td key={cell}>{String(value)}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {!answer?.sql_rows?.length && analysis?.detected_tables?.length ? (
            <div className="table-list">
              {analysis.detected_tables.slice(0, 8).map((table) => (
                <article key={String(table.table_name)}>
                  <strong>{String(table.table_name)}</strong>
                  <p>{String(table.row_count)} rows · {Array.isArray(table.columns) ? table.columns.join(", ") : ""}</p>
                </article>
              ))}
            </div>
          ) : null}
          {(answer?.graph?.nodes?.length || analysis?.graph?.nodes?.length) ? (
            <div className="graph-cloud">
              {(answer?.graph?.nodes ?? analysis?.graph?.nodes ?? []).slice(0, 24).map((node) => <span key={String(node.id)}>{String(node.label)}</span>)}
            </div>
          ) : <p className="muted">Generated SQL and graph entities appear when those routes activate.</p>}
          {analysis?.graph?.edges?.length ? <p className="muted">{analysis.graph.edges.length} graph relationship edges detected.</p> : null}
        </Panel>
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
