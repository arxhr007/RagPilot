import type { ChatResponse, IngestResponse, RouteOverride } from "../types/ragpilot";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || response.statusText);
  }
  return response.json() as Promise<T>;
}

export async function uploadFiles(files: FileList): Promise<IngestResponse> {
  const form = new FormData();
  Array.from(files).forEach((file) => form.append("files", file));
  return parse<IngestResponse>(
    await fetch(`${API_BASE}/api/upload`, {
      method: "POST",
      body: form,
    }),
  );
}

export async function ingestUrl(url: string, maxPages: number, usePlaywright = false): Promise<IngestResponse> {
  return parse<IngestResponse>(
    await fetch(`${API_BASE}/api/ingest/url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, max_pages: maxPages, use_playwright: usePlaywright }),
    }),
  );
}

export async function chat(datasetId: string, question: string, routeOverride: RouteOverride): Promise<ChatResponse> {
  return parse<ChatResponse>(
    await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset_id: datasetId, question, route_override: routeOverride }),
    }),
  );
}
