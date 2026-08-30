const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  role: ChatRole;
  content: string;
}

export interface Source {
  title: string;
  url: string;
}

export interface LivePage {
  title: string;
  url: string;
  body: string;
}

export interface ProgramOptionsResponse {
  programs: [string, string][];
  countries: [string, string][];
}

export interface ScrapeRequest {
  program_type_label: string;
  program_type_slug: string;
  program_label: string;
  country_code: string;
  country_label_by_code: Record<string, string>;
}

export interface ChatRequest {
  question: string;
  chat_history: ChatMessage[];
  live_page: LivePage | null;
}

export interface ChatResponse {
  reply: string;
  sources: Source[];
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers || {}),
      },
    });
  } catch {
    throw new Error(
      `Could not reach the backend at ${API_BASE_URL}. Is it running? (uvicorn backend.main:app --reload --port 8000)`
    );
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

export function getProgramTypes(): Promise<Record<string, string>> {
  return apiFetch<Record<string, string>>("/api/program-types");
}

export function getProgramOptions(programTypeSlug: string): Promise<ProgramOptionsResponse> {
  const params = new URLSearchParams({ program_type_slug: programTypeSlug });
  return apiFetch<ProgramOptionsResponse>(`/api/program-options?${params.toString()}`);
}

export function scrapeSelection(req: ScrapeRequest): Promise<LivePage> {
  return apiFetch<LivePage>("/api/scrape", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export function sendChat(req: ChatRequest): Promise<ChatResponse> {
  return apiFetch<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify(req),
  });
}
