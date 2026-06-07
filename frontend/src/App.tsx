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
} from "lucide-react";
import { AnimatedGrid } from "./components/AnimatedGrid";
import { chat, ingestUrl, uploadFiles } from "./services/api";
import type { Architecture, ChatResponse, DatasetAnalysis, IngestResponse, RouteOverride } from "./types/ragpilot";
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

function estimateTokens(text = "") {
  return Math.ceil(text.length / 4);
}

function formatNumber(value?: number) {
  return Math.round(value ?? 0).toLocaleString();
}

function formatReduction(value?: number) {
  const reduction = Math.max(0, value ?? 0);
  if (reduction >= 99.5) return "99%";
  return `${formatNumber(reduction)}%`;
}

function timeLabel() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function contextBudget(analysis: DatasetAnalysis | null, answer: ChatResponse | null) {
  const datasetTokens = answer?.context_budget?.estimated_dataset_tokens ?? analysis?.token_metrics?.estimated_dataset_tokens ?? 0;
  const evidenceTokens = answer
    ? answer.context_budget?.estimated_evidence_tokens ?? estimateTokens(answer.sources?.map((source) => source.text).join("\n") ?? "")
    : 0;
  const savedTokens = answer && evidenceTokens > 0
    ? answer.context_budget?.estimated_saved_tokens ?? Math.max(0, datasetTokens - evidenceTokens)
    : 0;
  const reduction = answer && evidenceTokens > 0 && datasetTokens
    ? answer.context_budget?.reduction_percent ?? Math.round((savedTokens / datasetTokens) * 1000) / 10
    : 0;
  return { datasetTokens, evidenceTokens, savedTokens, reduction };
}

function dataSuggestions(analysis: DatasetAnalysis | null) {
  if (!analysis) return [];
  if (analysis.question_suggestions?.length) return analysis.question_suggestions.slice(0, 6);
  const suggestions: string[] = [];
  const tables = analysis.detected_tables ?? [];
  const entities = analysis.graph?.nodes ?? [];
  const modes = new Set(analysis.rag_modes_selected ?? []);
  const tableNames = tables.map((table) => String(table.source_name || table.table_name || "").toLowerCase()).join(" ");
  const columns = tables.flatMap((table) => Array.isArray(table.columns) ? table.columns.map(String) : []);
  const columnText = columns.join(" ").toLowerCase();

  if (columnText.includes("speaker") || tableNames.includes("event")) suggestions.push("List the event speakers");
  if (columnText.includes("venue")) suggestions.push("Where is the event venue?");
  if (columnText.includes("product")) suggestions.push("How many active products are listed?");
  if (columnText.includes("owner") || columnText.includes("team")) suggestions.push("Which team owns a product in this data?");
  if (modes.has("graph") && entities.length) suggestions.push(`Which systems are connected to ${String(entities[0].label ?? entities[0].id)}?`);
  if (modes.has("keyword")) suggestions.push("What exact contacts, IDs, or codes are listed?");
  if (modes.has("hierarchical")) suggestions.push("Summarize the longest policy or handbook section");
  if (modes.has("semantic")) suggestions.push("Summarize the main narrative sections");

  return Array.from(new Set(suggestions)).slice(0, 6);
}

function scrapedPages(analysis: DatasetAnalysis | null) {
  return (analysis?.detected_inputs ?? [])
    .filter((input) => input.kind === "website")
    .flatMap((input) => Array.isArray(input.scraped_pages) ? input.scraped_pages : []);
}

function websiteInputs(analysis: DatasetAnalysis | null) {
  return (analysis?.detected_inputs ?? []).filter((input) => input.kind === "website");
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

function GraphRagViz({ graph }: { graph?: { nodes?: Array<Record<string, unknown>>; edges?: Array<Record<string, unknown>> } | null }) {
  const nodes = (graph?.nodes ?? []).slice(0, 18);
  const nodeIds = new Set(nodes.map((node) => String(node.id ?? node.label)));
  const edges = (graph?.edges ?? [])
    .filter((edge) => nodeIds.has(String(edge.source)) && nodeIds.has(String(edge.target)))
    .slice(0, 32);

  if (!nodes.length) {
    return <p className="muted">Graph RAG visualization appears after entity relationships are extracted.</p>;
  }

  const center = { x: 220, y: 145 };
  const radius = nodes.length > 10 ? 112 : 96;
  const positioned = nodes.map((node, index) => {
    const angle = (Math.PI * 2 * index) / nodes.length - Math.PI / 2;
    const weight = Number(node.weight ?? 1);
    return {
      id: String(node.id ?? node.label),
      label: String(node.label ?? node.id),
      type: String(node.type ?? "Entity"),
      weight,
      x: center.x + Math.cos(angle) * radius,
      y: center.y + Math.sin(angle) * radius,
      r: Math.min(21, 8 + weight * 2),
    };
  });
  const byId = new Map(positioned.map((node) => [node.id, node]));
  const typeCounts = positioned.reduce<Record<string, number>>((acc, node) => {
    acc[node.type] = (acc[node.type] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="graph-viz">
      <svg viewBox="0 0 440 290" role="img" aria-label="Graph RAG entity relationship visualization">
        <defs>
          <filter id="graphGlow" x="-50%" y="-50%" width="200%" height="200%">
            <feDropShadow dx="0" dy="8" stdDeviation="8" floodColor="#063b91" floodOpacity="0.18" />
          </filter>
        </defs>
        {edges.map((edge, index) => {
          const source = byId.get(String(edge.source));
          const target = byId.get(String(edge.target));
          if (!source || !target) return null;
          const weight = Math.min(4, Math.max(1, Number(edge.weight ?? 1)));
          return (
            <line
              key={`${source.id}-${target.id}-${index}`}
              x1={source.x}
              y1={source.y}
              x2={target.x}
              y2={target.y}
              stroke="#8abfff"
              strokeWidth={weight}
              strokeOpacity="0.52"
            />
          );
        })}
        {positioned.map((node) => (
          <g key={node.id} filter="url(#graphGlow)">
            <circle className={`graph-node graph-node-${node.type.toLowerCase()}`} cx={node.x} cy={node.y} r={node.r} />
            <text x={node.x} y={node.y + node.r + 13} textAnchor="middle">{node.label.length > 18 ? `${node.label.slice(0, 16)}...` : node.label}</text>
          </g>
        ))}
      </svg>
      <div className="graph-legend">
        {Object.entries(typeCounts).map(([type, count]) => (
          <span key={type}>{type}: {count}</span>
        ))}
      </div>
      <p className="muted">{nodes.length} entities and {edges.length} visible relationships. Edges show co-occurrence evidence used by Graph RAG.</p>
    </div>
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
        {budget.evidenceTokens > 0
          ? <>RAGPilot used ~{formatNumber(budget.evidenceTokens)} evidence tokens instead of sending ~{formatNumber(budget.datasetTokens)} raw dataset tokens.</>
          : <>RAGPilot did not send retrieved evidence for this answer.</>}
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
  suggestions,
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
  suggestions: string[];
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
        <h1>RAGPilot</h1>
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
        {suggestions.length > 0 && (
          <div className="chat-suggestions">
            {suggestions.map((suggestion) => (
              <button className="ghost-button" key={suggestion} disabled={busy} onClick={() => setQuestion(suggestion)}>
                {suggestion}
              </button>
            ))}
          </div>
        )}
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
  const [usePlaywright, setUsePlaywright] = useState(false);
  const [question, setQuestion] = useState("");
  const [routeOverride, setRouteOverride] = useState<RouteOverride>("auto");
  const [busy, setBusy] = useState(false);
  const [ingestLog, setIngestLog] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [page, setPage] = useState(() => window.location.pathname === "/chat" ? "/chat" : "/");

  const activeNodes = useMemo(() => architecture?.workflow_nodes ?? analysis?.activated_nodes ?? [], [architecture, analysis]);
  const budget = contextBudget(analysis, answer);
  const suggestions = useMemo(() => dataSuggestions(analysis), [analysis]);
  const websitePages = useMemo(() => scrapedPages(analysis), [analysis]);
  const websites = useMemo(() => websiteInputs(analysis), [analysis]);

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

  function pushIngestLog(message: string) {
    setIngestLog((items) => [...items.slice(-7), `[${timeLabel()}] ${message}`]);
  }

  function summarizeIngest(res: IngestResponse) {
    const pages = scrapedPages(res.analysis).length;
    const tables = res.analysis.detected_tables?.length ?? 0;
    const segments = res.analysis.segments?.length ?? 0;
    const modes = res.analysis.rag_modes_selected?.join(", ") || res.analysis.selected_strategy;
    if (pages) pushIngestLog(`Scraped ${pages} page(s) and extracted website text.`);
    pushIngestLog(`Classified ${segments} segment(s), found ${tables} table(s), activated ${modes}.`);
    pushIngestLog(`Ready. Dataset ${res.dataset_id.slice(0, 8)} is indexed for chat.`);
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

  async function runIngest(task: () => Promise<IngestResponse>, startMessages: string[]) {
    setBusy(true);
    setError("");
    setIngestLog([]);
    startMessages.forEach(pushIngestLog);
    try {
      const result = await task();
      pushIngestLog("Response received. Building dashboard analysis.");
      acceptIngest(result);
      summarizeIngest(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong";
      setError(message);
      pushIngestLog(`Error: ${message}`);
    } finally {
      setBusy(false);
    }
  }

  function askCurrent(override: RouteOverride = routeOverride) {
    run(() => chat(datasetId, question, override), setAnswer);
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
        suggestions={suggestions}
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
            <h1>RAGPilot</h1>
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
            <p>RAGPilot segments any upload, selects the right RAG module for each data type, then sends the right evidence to the LLM.</p>
          </div>
          <div className="value-cards">
            <MetricCard label="Analyze Any Data" value={analysis ? formatNumber(Number(analysis.characteristics.segment_count ?? 0)) : "PDF/CSV/Web"} note="Documents, tables, websites, reports" />
            <MetricCard label="Route To The Right RAG" value={analysis ? formatNumber(analysis.rag_modes_selected.length) : "6 modes"} note="Semantic, SQL, graph, keyword, hierarchical, hybrid" />
            <MetricCard label="Answer With Less Context" value={answer ? formatReduction(budget.reduction) : "Ask first"} note="Estimated context reduction after retrieval" />
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
                  const files = Array.from(event.target.files);
                  runIngest(
                    () => uploadFiles(event.target.files!),
                    [
                      `Preparing ${files.length} file(s): ${files.map((file) => file.name).join(", ")}`,
                      "Uploading files to FastAPI backend.",
                      "Extracting text/tables and classifying each region into RAG methods.",
                    ],
                  );
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
              <button disabled={!url || busy} onClick={() => runIngest(
                () => ingestUrl(url, maxPages, usePlaywright),
                [
                  `Starting recursive crawl for ${url}.`,
                  `Target: up to ${maxPages} page(s). ${usePlaywright ? "Playwright rendering enabled." : "Requests/BeautifulSoup mode."}`,
                  "Discovering links, extracting page text, and preparing RAG chunks.",
                ],
              )}>
                {busy ? <Loader2 className="spin" size={16} /> : <Search size={16} />}
                Ingest
              </button>
            </div>
            <label className="toggle-row">
              <input type="checkbox" checked={usePlaywright} onChange={(event) => setUsePlaywright(event.target.checked)} />
              <span>Use Playwright for JS-heavy pages</span>
            </label>
            {ingestLog.length > 0 && (
              <div className="ingest-log">
                <div className="segment-head">
                  <strong>Ingest Log</strong>
                  {busy ? <span>running</span> : <span>done</span>}
                </div>
                {ingestLog.map((item, index) => <p key={`${item}-${index}`}>{item}</p>)}
              </div>
            )}
            {websitePages.length > 0 && (
              <div className="scraped-pages">
                <div className="segment-head">
                  <strong>Scraped Pages</strong>
                  <span>{websitePages.length} / {String(websites[0]?.requested_pages ?? websitePages.length)}</span>
                </div>
                {Boolean(websites[0]?.crawl_message) && <p className="muted">{String(websites[0]?.crawl_message)}</p>}
                {websitePages.slice(0, 10).map((page, index) => (
                  <article key={`${String((page as Record<string, unknown>).url)}-${index}`}>
                    <strong>{String((page as Record<string, unknown>).title || "Untitled page")}</strong>
                    <a href={String((page as Record<string, unknown>).url)} target="_blank" rel="noreferrer">
                      {String((page as Record<string, unknown>).url)}
                    </a>
                    <small>
                      {formatNumber(Number((page as Record<string, unknown>).text_chars ?? 0))} chars
                      {Number((page as Record<string, unknown>).document_link_count ?? 0) > 0
                        ? ` - ${String((page as Record<string, unknown>).document_link_count)} document links`
                        : ""}
                    </small>
                  </article>
                ))}
              </div>
            )}
            <div className="demo-row">
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
              <MetricCard label="Saved Tokens" value={answer ? `~${formatNumber(budget.savedTokens)}` : "Ask first"} note="Estimated avoided context" />
              <MetricCard label="Reduction" value={answer ? formatReduction(budget.reduction) : "Ask first"} note="Small-model context focus" />
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

          <Panel title="RAG Method Map" icon={<Activity size={18} />}>
            {analysis?.method_assignments?.length ? (
              <>
                <div className="classification-summary">
                  {Object.entries(analysis.rag_classification_summary?.counts ?? {}).map(([mode, count]) => (
                    <span key={mode}>{mode}: <b>{count}</b></span>
                  ))}
                </div>
                <div className="method-list">
                  {analysis.method_assignments.slice(0, 20).map((item, idx) => {
                    const secondary = Array.isArray(item.secondary_rags) ? item.secondary_rags : [];
                    const signals = Array.isArray(item.signals) ? item.signals : [];
                    return (
                      <article key={`${String(item.title)}-${idx}`}>
                        <div className="segment-head">
                          <strong>{String(item.title)}</strong>
                          <span>{String(item.primary_rag ?? item.method)} - {Math.round(Number(item.confidence ?? 0) * 100)}%</span>
                        </div>
                        <div className="classifier-line">
                          <span>{String(item.classifier ?? "heuristic").replaceAll("_", " ")}</span>
                          {secondary.map((mode) => <i key={String(mode)}>+ {String(mode)}</i>)}
                        </div>
                        <p>{String(item.segment_type)} - {String(item.decision_reason || item.reason || "Selected from detected structure and query signals.")}</p>
                        {signals.length > 0 && <small>Signals: {signals.map(String).join(", ")}</small>}
                        {Boolean(item.table_name) && <small>SQLite table: {String(item.table_name)}</small>}
                      </article>
                    );
                  })}
                </div>
              </>
            ) : <p className="muted">Upload data to see which RAG method is assigned to each section.</p>}
          </Panel>

          <Panel title="Ask" icon={<MessageSquare size={18} />}>
            <select className="route-select" value={routeOverride} onChange={(event) => setRouteOverride(event.target.value as RouteOverride)}>
              {["auto", "semantic", "sql", "graph", "keyword", "hierarchical", "hybrid"].map((mode) => (
                <option value={mode} key={mode}>{mode === "auto" ? "Auto route" : mode}</option>
              ))}
            </select>
            <div className="ask-row">
              <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={analysis ? "Ask a question from this dataset..." : "Upload data first, then ask..."} />
              <button disabled={!datasetId || !question || busy} onClick={() => askCurrent()}>
                {busy ? <Loader2 className="spin" size={16} /> : <Send size={16} />}
                Ask
              </button>
            </div>
            <div className="demo-questions">
              {analysis?.question_suggestion_source && <span className="suggestion-source">Suggestions: {analysis.question_suggestion_source.replaceAll("_", " ")}</span>}
              {suggestions.map((suggestion) => (
                <button className="ghost-button" key={suggestion} disabled={busy} onClick={() => setQuestion(suggestion)}>
                  {suggestion}
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
            ) : <p className="muted">RAGPilot will list detected sections and selected RAG modules here.</p>}
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

          <Panel title="SQL Evidence" icon={<Database size={18} />}>
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
            {!answer?.generated_sql && !analysis?.detected_tables?.length ? <p className="muted">Generated SQL and result rows appear when SQL RAG activates.</p> : null}
          </Panel>

          <Panel title="Graph RAG" icon={<GitBranch size={18} />}>
            <GraphRagViz graph={answer?.graph ?? analysis?.graph} />
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
