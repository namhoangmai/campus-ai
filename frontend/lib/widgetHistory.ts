/**
 * Browser-local conversation history for the chat widget.
 *
 * There is no server-side identity for the widget at all (it's authenticated per-request by a
 * widget key, not a logged-in user — see ARCHITECTURE.md §8), so this is device/browser-local by
 * design: no backend call, no cross-device sync. Every key is namespaced by widgetKey
 * (`campus-ai:history:<widgetKey>`) because a browser that has opened more than one tenant's
 * widget shares one localStorage origin (`NEXT_PUBLIC_API_URL`'s frontend origin) across all of
 * them — without the namespace, one tenant's students would see another tenant's saved
 * conversation titles and content.
 *
 * Every read/write is wrapped in try/catch and never throws: the widget is loaded in an iframe on
 * someone else's site, where storage can be partitioned, blocked, or throw on write (private
 * browsing, quota exceeded, third-party storage blocked). On any failure this module just acts
 * like there's no saved history — the widget's normal in-memory chat still works.
 */

import { ChatMessage, Source } from "./api";

export interface StoredMessage extends ChatMessage {
  sources?: Source[];
}

export interface StoredConversation {
  id: string;
  title: string;
  updatedAt: number;
  messages: StoredMessage[];
}

const MAX_CONVERSATIONS = 20;
const TITLE_MAX_LENGTH = 60;

function historyKey(widgetKey: string): string {
  return `campus-ai:history:${widgetKey}`;
}

export function isStorageAvailable(): boolean {
  try {
    const probeKey = "campus-ai:storage-check";
    window.localStorage.setItem(probeKey, "1");
    window.localStorage.removeItem(probeKey);
    return true;
  } catch {
    return false;
  }
}

export function loadConversations(widgetKey: string): StoredConversation[] {
  try {
    const raw = window.localStorage.getItem(historyKey(widgetKey));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed as StoredConversation[];
  } catch {
    return [];
  }
}

export function saveConversation(widgetKey: string, conversation: StoredConversation): void {
  try {
    const rest = loadConversations(widgetKey).filter((c) => c.id !== conversation.id);
    const next = [conversation, ...rest]
      .sort((a, b) => b.updatedAt - a.updatedAt)
      .slice(0, MAX_CONVERSATIONS);
    window.localStorage.setItem(historyKey(widgetKey), JSON.stringify(next));
  } catch {
    // Storage unavailable or over quota — drop the save silently, chat stays in-memory only.
  }
}

export function deleteConversation(widgetKey: string, id: string): void {
  try {
    const next = loadConversations(widgetKey).filter((c) => c.id !== id);
    window.localStorage.setItem(historyKey(widgetKey), JSON.stringify(next));
  } catch {
    // Storage unavailable — nothing to delete, chat stays in-memory only.
  }
}

export function makeConversationId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
}

export function titleFromMessages(messages: StoredMessage[]): string {
  const firstUser = messages.find((m) => m.role === "user");
  const text = firstUser?.content.trim() || "New conversation";
  return text.length > TITLE_MAX_LENGTH ? `${text.slice(0, TITLE_MAX_LENGTH - 3)}...` : text;
}

export function formatRelativeTime(timestamp: number): string {
  const diffMs = Date.now() - timestamp;
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;

  if (diffMs < minute) return "just now";
  if (diffMs < hour) return `${Math.floor(diffMs / minute)}m ago`;
  if (diffMs < day) return `${Math.floor(diffMs / hour)}h ago`;
  return `${Math.floor(diffMs / day)}d ago`;
}
