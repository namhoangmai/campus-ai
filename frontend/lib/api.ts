/**
 * Backend API client for the widget chat UI.
 *
 * Replaces v1's api.ts, which mixed chat calls with TU/e-scraping-specific calls
 * (getProgramTypes/getProgramOptions/scrapeSelection) that no longer exist on the v2 backend
 * (ARCHITECTURE.md §7 — those endpoints were retired with the scraping pipeline). The one call
 * that remains, sendChat, now requires a widget key: every request carries `X-Widget-Key`, and
 * the response's Source shape now covers both markdown (url) and PDF (page) citations instead
 * of assuming every source has a URL.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  role: ChatRole;
  content: string;
}

export interface Source {
  title: string;
  doc_type: "markdown" | "pdf";
  url: string | null;
  page: number | null;
}

export interface ChatRequest {
  question: string;
  chat_history: ChatMessage[];
}

export interface ChatResponse {
  reply: string;
  sources: Source[];
}

async function apiFetch<T>(path: string, widgetKey: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-Widget-Key": widgetKey,
        ...(init?.headers || {}),
      },
    });
  } catch {
    throw new Error(`Could not reach the Campus-AI backend at ${API_BASE_URL}. Is it running?`);
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // response body wasn't JSON; fall back to statusText
    }
    throw new Error(detail);
  }

  return res.json() as Promise<T>;
}

export function sendChat(widgetKey: string, req: ChatRequest): Promise<ChatResponse> {
  return apiFetch<ChatResponse>("/api/chat", widgetKey, {
    method: "POST",
    body: JSON.stringify(req),
  });
}
