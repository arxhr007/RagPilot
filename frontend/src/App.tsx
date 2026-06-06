import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  Database,
  FileUp,
  Globe,
  GitBranch,
  LayoutDashboard,
  Loader2,
  MessageSquare,
  Route,
  Search,
  Send,
  Sparkles,
} from "lucide-react";
import { AnimatedGrid } from "./components/AnimatedGrid";
import { chat, ingestUrl, loadUniversalDemo, uploadFiles } from "./services/api";
import type { Architecture, ChatResponse, DatasetAnalysis, IngestResponse, RouteOverride } from "./types/ragx";
import "./styles.css";

const DEMO_QUESTIONS = [
  "Who is the CEO?",
  "Which products are connected to BeaconAI?",
  "How many products are active?",
  "List the event speakers",
  "Which team owns AtlasFlow?",
];

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

function estimateTokens(text = "") {
  return Math.ceil(text.length / 4);
}

function formatNumber(value?: number) {
  return Math.round(value ?? 0).toLocaleString();
}

function contextBudget(analysis: DatasetAnalysis | null, answer: ChatResponse | null) {
  const datasetTokens = answer?.context_budget?.estimated_dataset_tokens ?? analysis?.token_metrics?.estimated_dataset_tokens ?? 0;
  const evidenceTokens = answer?.context_budget?.estimated_evidence_tokens ?? estimateTokens(answer?.sources?.map((source) => source.text).join("\n") ?? "");
  const savedTokens = answer?.context_budget?.estimated_saved_tokens ?? Math.max(0, datasetTokens - evidenceTokens);
  const reduction = answer?.context_budget?.reduction_percent ?? (datasetTokens ? Math.round((savedTokens / datasetTokens) * 1000) / 10 : 0);
  return { datasetTokens, evidenceTokens, savedTokens, reduction };
}

function MetricCard({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <article className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </article>
  );
}

function AnswerBlock({ answer, analysis }: { answer: ChatResponse | null; analysis: DatasetAnalysis | null }) {
  if (!answer) return null;
  const budget = contextBudget(analysis, answer);
  return (
    <div className="answer">
      <div className={`validation ${answer.answer_validation?.status ?? "grounded"}`}>
        {(answer.answer_validation?.status ?? "grounded").replaceAll("_", " ")} - answer confidence {Math.round((answer.answer_confidence ?? 0) * 100)}%
      </div>
      <p className="final-answer">{answer.answer}</p>
      <p className="budget-line">
        RAGX used ~{formatNumber(budget.evidenceTokens)} evidence tokens instead of sending ~{formatNumber(budget.datasetTokens)} raw dataset tokens.
      </p>
      <div className="route-line">
        <strong>{answer.route.toUpperCase()}</strong>
        <Confidence value={answer.confidence} />
      </div>
      <p className="muted">{answer.route_reason}</p>
      <div className="modules">
        {answer.retrievers_used.map((retriever) => <span className="active-mode" key={retriever}>{retriever}</span>)}
      </div>
      <p className="muted">Intent: {answer.query_intent} - normalized: {answer.normalized_query} - candidates: {answer.candidate_count}</p>
      {answer.fact_match && (
        <p className="muted">Fact match: {answer.fact_match.fact_type} - {answer.fact_match.subject} {"->"} {answer.fact_match.object}</p>
      )}
      {answer.retrievers_skipped.length > 0 && (
        <details className="skipped">
          <summary>Skipped retrievers</summary>
          <ul className="clean-list">
            {answer.retrievers_skipped.map((item, idx) => (
              <li key={idx}>{item.retriever}: {item.reason}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function CleanChatPage({
  datasetId,
  question,
  setQuestion,
  answer,
  analysis,
  busy,
  error,
  ask,
  navigate,
}: {
  datasetId: string;
  question: string;
  setQuestion: (value: string) => void;
  answer: ChatResponse | null;
  analysis: DatasetAnalysis | null;
  busy: boolean;
  error: string;
  ask: () => void;
  navigate: (path: string) => void;
}) {
  return (
    <main className="shell chat-shell">
      <AnimatedGrid />
      <div className="chat-actions">
        <button className="ghost-button" onClick={() => navigate("/")}>
          <FileUp size={14} />
          Add Data
        </button>
        <button className="ghost-button" onClick={() => navigate("/")}>
          <LayoutDashboard size={14} />
          Dashboard
        </button>
      </div>
      <section className="chat-stage">
        <h1>RAGX</h1>
        <p>Ask anything from your uploaded dataset.</p>
        {!datasetId && <div className="chat-empty">Add data in the dashboard to start chatting.</div>}
        {error && <div className="error chat-error">{error}</div>}
        <div className="chat-input">
          <input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask a grounded question..."
            onKeyDown={(event) => {
              if (event.key === "Enter" && datasetId && question && !busy) ask();
            }}
          />
          <button disabled={!datasetId || !question || busy} onClick={ask} aria-label="Send question">
            {busy ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
          </button>
        </div>
        <AnswerBlock answer={answer} analysis={analysis} />
      </section>
    </main>
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
  const [page, setPage] = useState(() => window.location.pathname === "/chat" ? "/chat" : "/");

  const activeNodes = useMemo(() => architecture?.workflow_nodes ?? analysis?.activated_nodes ?? [], [architecture, analysis]);
  const budget = contextBudget(analysis, answer);

  useEffect(() => {
    const onPopState = () => setPage(window.location.pathname === "/chat" ? "/chat" : "/");
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  function navigate(path: string) {
    window.history.pushState({}, "", path);
    setPage(path === "/chat" ? "/chat" : "/");
  }

  function acceptIngest(res: IngestResponse) {
    setDatasetId(res.dataset_id);
    setAnalysis(res.analysis);
    setArchitecture(res.architecture);
    setAnswer(null);
  }

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

  function askCurrent(override: RouteOverride = routeOverride) {
    run(() => chat(datasetId, question, override), setAnswer);
  }

  function askDemo(demoQuestion: string) {
    setQuestion(demoQuestion);
    if (datasetId) run(() => chat(datasetId, demoQuestion, "auto"), setAnswer);
  }

  if (page === "/chat") {
    return (
      <CleanChatPage
        datasetId={datasetId}
        question={question}
        setQuestion={setQuestion}
        answer={answer}
        analysis={analysis}
        busy={busy}
        error={error}
        ask={() => askCurrent("auto")}
        navigate={navigate}
      />
    );
  }

  return (
    <main className="shell">
      <AnimatedGrid />
      <div className="app-layer">
        <header className="topbar">
          <div>
            <p className="eyebrow">Adaptive Multi-RAG Orchestrator</p>
            <h1>RAGX</h1>
          </div>
          <div className="top-actions">
            {datasetId && (
              <button className="ghost-button" onClick={() => navigate("/chat")}>
                <MessageSquare size={15} />
                Open Chat
              </button>
            )}
            <div className="status">
              {datasetId ? `Dataset ${datasetId.slice(0, 8)}` : "No dataset loaded"}
            </div>
          </div>
        </header>

        <section className="story-panel">
          <div>
            <p className="eyebrow">Token-efficient grounded answers</p>
            <h2>Make a small LLM reason over big messy data.</h2>
            <p>RAGX segments any upload, picks the right retrieval method, and sends only the strongest evidence into context.</p>
          </div>
          <div className="value-cards">
            <MetricCard label="Analyze Any Data" value={analysis ? formatNumber(Number(analysis.characteristics.segment_count ?? 0)) : "PDF/CSV/Web"} note="Documents, tables, websites, reports" />
            <MetricCard label="Route To The Right RAG" value={analysis ? formatNumber(analysis.rag_modes_selected.length) : "6 modes"} note="Semantic, SQL, graph, keyword, hierarchical, hybrid" />
            <MetricCard label="Answer With Less Context" value={analysis ? `${formatNumber(budget.reduction)}%` : "Less tokens"} note="Estimated context reduction after retrieval" />
          </div>
          <div className="workflow-strip">
            {["Segment", "Classify", "Route", "Retrieve", "Synthesize", "Validate"].map((step) => <span key={step}>{step}</span>)}
          </div>
        </section>

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
                  run(() => uploadFiles(event.target.files!), acceptIngest);
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
              <button disabled={!url || busy} onClick={() => run(() => ingestUrl(url, maxPages), acceptIngest)}>
                {busy ? <Loader2 className="spin" size={16} /> : <Search size={16} />}
                Ingest
              </button>
            </div>
            <div className="demo-row">
              <button className="ghost-button" disabled={busy} onClick={() => run(loadUniversalDemo, acceptIngest)}>
                <Sparkles size={15} />
                Load Demo Dataset
              </button>
              {datasetId && (
                <button className="ghost-button" onClick={() => navigate("/chat")}>
                  <MessageSquare size={15} />
                  Open Chat
                </button>
              )}
            </div>
          </Panel>

          <Panel title="Context Budget" icon={<Activity size={18} />}>
            <div className="metric-grid">
              <MetricCard label="Dataset Tokens" value={`~${formatNumber(budget.datasetTokens)}`} note="Estimated raw context" />
              <MetricCard label="Evidence Tokens" value={`~${formatNumber(budget.evidenceTokens)}`} note="Retrieved for the answer" />
              <MetricCard label="Saved Tokens" value={`~${formatNumber(budget.savedTokens)}`} note="Estimated avoided context" />
              <MetricCard label="Reduction" value={`${formatNumber(budget.reduction)}%`} note="Small-model context focus" />
            </div>
            <p className="muted">Token counts are transparent estimates using roughly four characters per token.</p>
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
                        <p>{String(table.row_count)} rows - {Array.isArray(table.columns) ? table.columns.join(", ") : ""}</p>
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
                    <span key={String(module.name)}>{String(module.name)} - {String(module.status)}</span>
                  ))}
                </div>
                <div className="workflow">
                  {activeNodes.map((node) => <span key={node}>{node}</span>)}
                </div>
              </>
            ) : <p className="muted">RAGX will show the activated pipeline here.</p>}
          </Panel>

          <Panel title="RAG Method Map" icon={<Activity size={18} />}>
            {analysis?.method_assignments?.length ? (
              <div className="method-list">
                {analysis.method_assignments.slice(0, 20).map((item, idx) => (
                  <article key={`${String(item.title)}-${idx}`}>
                    <div className="segment-head">
                      <strong>{String(item.title)}</strong>
                      <span>{String(item.method)} - {Math.round(Number(item.confidence ?? 0) * 100)}%</span>
                    </div>
                    <p>{String(item.segment_type)} - {String(item.reason || "Selected from detected structure and query signals.")}</p>
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
              <button disabled={!datasetId || !question || busy} onClick={() => askCurrent()}>
                {busy ? <Loader2 className="spin" size={16} /> : <Send size={16} />}
                Ask
              </button>
            </div>
            <div className="demo-questions">
              {DEMO_QUESTIONS.map((demoQuestion) => (
                <button className="ghost-button" key={demoQuestion} disabled={busy} onClick={() => askDemo(demoQuestion)}>
                  {demoQuestion}
                </button>
              ))}
            </div>
            <AnswerBlock answer={answer} analysis={analysis} />
          </Panel>

          <Panel title="Segments" icon={<Activity size={18} />}>
            {analysis?.segments?.length ? (
              <div className="segments">
                {analysis.segments.slice(0, 18).map((segment) => (
                  <article key={segment.id}>
                    <div className="segment-head">
                      <strong>{segment.title}</strong>
                      <span>{segment.rag_module} - {Math.round(segment.confidence * 100)}%</span>
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
                    <p>{String(table.row_count)} rows - {Array.isArray(table.columns) ? table.columns.join(", ") : ""}</p>
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
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
