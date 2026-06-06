export type RagStrategy = "semantic" | "sql" | "graph" | "keyword" | "hierarchical" | "hybrid";
export type RouteOverride = "auto" | RagStrategy;

export interface Segment {
  id: string;
  source_name: string;
  title: string;
  segment_type: string;
  rag_module: RagStrategy;
  confidence: number;
  reasons: string[];
  text_preview: string;
  table_name?: string | null;
  metadata: Record<string, unknown>;
}

export interface Source {
  id: string;
  title: string;
  url?: string | null;
  file_name?: string | null;
  text: string;
  score: number;
  match_reason: string;
}

export interface ExtractedFact {
  id: string;
  fact_type: string;
  subject: string;
  predicate: string;
  object: string;
  qualifier: string;
  source_id: string;
  source_name: string;
  confidence: number;
  text: string;
}

export interface DatasetAnalysis {
  dataset_id: string;
  detected_inputs: Array<Record<string, unknown>>;
  characteristics: Record<string, unknown>;
  selected_strategy: RagStrategy;
  confidence: number;
  reasons: string[];
  tradeoffs: string[];
  activated_nodes: string[];
  segments: Segment[];
  rag_modes_available: RagStrategy[];
  rag_modes_selected: RagStrategy[];
  detected_tables: Array<Record<string, unknown>>;
  entity_types: Record<string, number>;
  graph: { nodes?: Array<Record<string, unknown>>; edges?: Array<Record<string, unknown>> };
  method_assignments: Array<Record<string, unknown>>;
  route_policy_summary: string;
  rag_classification_summary?: {
    counts?: Record<string, number>;
    classifier_sources?: Record<string, number>;
    warnings?: string[];
  };
  token_metrics?: {
    estimated_dataset_tokens?: number;
    estimated_chunk_count?: number;
    estimated_table_tokens?: number;
  };
}

export interface Architecture {
  dataset_id: string;
  name: string;
  modules: Array<Record<string, unknown>>;
  workflow_nodes: string[];
  explanation: string;
}

export interface IngestResponse {
  dataset_id: string;
  analysis: DatasetAnalysis;
  architecture: Architecture;
}

export interface ChatResponse {
  dataset_id: string;
  question: string;
  answer: string;
  route: RagStrategy;
  confidence: number;
  route_reason: string;
  normalized_query: string;
  expanded_query: string;
  query_intent: string;
  direct_answer: string;
  answer_confidence: number;
  answer_validation: { status?: string; reasons?: string[] };
  sources: Source[];
  reranked_sources: Source[];
  candidate_count: number;
  fact_match?: ExtractedFact | null;
  generated_sql?: string | null;
  sql_rows: Array<Record<string, unknown>>;
  graph?: { nodes: Array<Record<string, unknown>>; edges: Array<Record<string, unknown>> } | null;
  retrievers_used: RagStrategy[];
  retrievers_skipped: Array<Record<string, string>>;
  context_budget?: {
    estimated_dataset_tokens?: number;
    estimated_evidence_tokens?: number;
    estimated_saved_tokens?: number;
    reduction_percent?: number;
  };
}
