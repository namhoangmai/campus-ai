"use client";

/**
 * The widget's chat UI. Loaded inside an iframe by widget-loader.js (see public/widget-loader.js
 * and ARCHITECTURE.md §8) once a visitor opens the chat bubble on a university's site — never
 * loaded directly by a host page's own JS, which is the whole point of the iframe boundary.
 *
 * Adapted from v1's app/page.tsx: the program-type/country selector and the "load program info"
 * scraping flow are gone entirely (that UI existed to drive v1's now-retired scraping pipeline —
 * see ARCHITECTURE.md §0). What's kept is the chat transcript and message-sending logic, largely
 * unchanged, plus a Source renderer that now branches on `doc_type` to show either a link
 * (markdown, when a source_url is known) or a page number (PDF) — v1 assumed every source had a
 * URL, which silently produced link-less citations for anything that didn't (documented as a
 * known v1 bug in ARCHITECTURE-ESSENTIALS.md).
 *
 * The widget key comes from this page's own `?key=` query parameter, set by the loader when it
 * builds the iframe `src` — never hardcoded, never read from anywhere else, so this same page
 * serves every tenant.
 *
 * Conversation history (see lib/widgetHistory.ts) is autosaved to localStorage, namespaced by
 * widget key, and offered back through a simple in-widget "History" list. It's browser-local
 * only — there's no server-side identity to sync it against — and every storage call is
 * best-effort: if it fails or isn't available, the widget just behaves like today, fully
 * in-memory.
 *
 * "Stop" only aborts this page's fetch — the backend's /api/chat is synchronous and
 * non-streaming, so the OpenRouter call already in flight server-side keeps running to
 * completion regardless; the abort just stops the widget from waiting on (or rendering) that
 * response. "Edit" on a past question truncates local state back to before that question, since
 * once it changes the old answer (and anything asked after it) no longer applies.
 */

import { Suspense, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useSearchParams } from "next/navigation";
import { ChatMessage, Source, isAbortError, sendChat } from "@/lib/api";
import {
  StoredConversation,
  deleteConversation,
  formatRelativeTime,
  isStorageAvailable,
  loadConversations,
  makeConversationId,
  saveConversation,
  titleFromMessages,
} from "@/lib/widgetHistory";

interface DisplayMessage extends ChatMessage {
  sources?: Source[];
}

// localStorage availability can only be known in the browser (private browsing, quota, or
// iframe storage partitioning all vary at runtime), so it's read via useSyncExternalStore rather
// than an effect + setState — this avoids a client/server hydration mismatch by rendering the
// `getServerSnapshot` value (false) until the client re-checks after mount.
function subscribeNever() {
  return () => {};
}

export default function WidgetPage() {
  return (
    <Suspense fallback={null}>
      <WidgetChat />
    </Suspense>
  );
}

function WidgetChat() {
  const searchParams = useSearchParams();
  const widgetKey = searchParams.get("key");

  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState(() => makeConversationId());
  const [showHistory, setShowHistory] = useState(false);
  const [conversations, setConversations] = useState<StoredConversation[]>([]);
  const storageAvailable = useSyncExternalStore(
    subscribeNever,
    isStorageAvailable,
    () => false,
  );
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!storageAvailable || !widgetKey || messages.length === 0) return;
    saveConversation(widgetKey, {
      id: conversationId,
      title: titleFromMessages(messages),
      updatedAt: Date.now(),
      messages,
    });
  }, [messages, storageAvailable, conversationId, widgetKey]);

  if (!widgetKey) {
    return (
      <div className="flex h-screen items-center justify-center p-4 text-sm text-neutral-500">
        Missing widget key — this page must be opened via the Campus-AI widget loader.
      </div>
    );
  }

  function handleToggleHistory() {
    if (!showHistory) {
      setConversations(loadConversations(widgetKey as string));
    }
    setShowHistory((prev) => !prev);
  }

  function handleSelectConversation(conversation: StoredConversation) {
    abortControllerRef.current?.abort();
    setMessages(conversation.messages);
    setConversationId(conversation.id);
    setChatError(null);
    setShowHistory(false);
  }

  function handleDeleteConversation(conversation: StoredConversation) {
    if (!window.confirm(`Delete "${conversation.title}"? This can't be undone.`)) return;
    deleteConversation(widgetKey as string, conversation.id);
    setConversations((prev) => prev.filter((c) => c.id !== conversation.id));
    // The autosave effect would otherwise re-save this id on the next message, silently
    // resurrecting a "deleted" conversation — reset to a fresh one instead.
    if (conversation.id === conversationId) {
      handleNewConversation();
    }
  }

  function handleNewConversation() {
    abortControllerRef.current?.abort();
    setMessages([]);
    setQuestion("");
    setChatError(null);
    setConversationId(makeConversationId());
    setShowHistory(false);
  }

  function handleEditMessage(index: number) {
    if (sending) return;
    const target = messages[index];
    if (target.role !== "user") return;
    setQuestion(target.content);
    setMessages((prev) => prev.slice(0, index));
    setChatError(null);
  }

  function handleStop() {
    abortControllerRef.current?.abort();
  }

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q || sending) return;

    const history = messages.map(({ role, content }) => ({ role, content }));
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setQuestion("");
    setChatError(null);
    setSending(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const { reply, sources } = await sendChat(
        widgetKey as string,
        { question: q, chat_history: history },
        controller.signal,
      );
      setMessages((prev) => [...prev, { role: "assistant", content: reply, sources }]);
    } catch (err) {
      if (!isAbortError(err)) {
        setChatError(err instanceof Error ? err.message : "Something went wrong.");
      }
    } finally {
      setSending(false);
      abortControllerRef.current = null;
    }
  }

  return (
    <div className="flex h-screen flex-col bg-white">
      <div className="flex items-center justify-between border-b border-neutral-200 px-3 py-2">
        <span className="text-xs text-neutral-400">Campus-AI</span>
        <div className="flex gap-2">
          {storageAvailable && (
            <button
              type="button"
              onClick={handleToggleHistory}
              className="rounded-md px-2 py-1 text-xs font-medium text-neutral-600 hover:bg-neutral-100"
            >
              {showHistory ? "Back to chat" : "History"}
            </button>
          )}
          <button
            type="button"
            onClick={handleNewConversation}
            className="rounded-md px-2 py-1 text-xs font-medium text-neutral-600 hover:bg-neutral-100"
          >
            New chat
          </button>
        </div>
      </div>

      {showHistory ? (
        <HistoryList
          conversations={conversations}
          onSelect={handleSelectConversation}
          onDelete={handleDeleteConversation}
        />
      ) : (
        <>
          <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
            {messages.length === 0 && (
              <p className="text-sm text-neutral-400">Ask a question about your university&apos;s documents below.</p>
            )}
            {messages.map((msg, i) => (
              <MessageBubble
                key={i}
                message={msg}
                onEdit={msg.role === "user" ? () => handleEditMessage(i) : undefined}
                editDisabled={sending}
              />
            ))}
            {sending && <p className="text-sm text-neutral-400">Thinking…</p>}
            {chatError && <p className="text-sm text-red-600">{chatError}</p>}
          </div>

          <form onSubmit={handleAsk} className="flex gap-2 border-t border-neutral-200 p-3">
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a question…"
              className="flex-1 rounded-lg border border-neutral-300 px-3 py-2 text-sm outline-none focus:border-neutral-500"
            />
            {sending ? (
              <button
                type="button"
                onClick={handleStop}
                className="rounded-lg border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-700 transition hover:bg-neutral-100"
              >
                Stop
              </button>
            ) : (
              <button
                type="submit"
                disabled={!question.trim()}
                className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Send
              </button>
            )}
          </form>
        </>
      )}
    </div>
  );
}

function HistoryList({
  conversations,
  onSelect,
  onDelete,
}: {
  conversations: StoredConversation[];
  onSelect: (conversation: StoredConversation) => void;
  onDelete: (conversation: StoredConversation) => void;
}) {
  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      <p className="mb-3 text-xs text-neutral-400">
        Saved on this device and browser only — conversations don&apos;t follow you to another
        device.
      </p>
      {conversations.length === 0 ? (
        <p className="text-sm text-neutral-400">No past conversations yet.</p>
      ) : (
        <ul className="space-y-2">
          {conversations.map((conversation) => (
            <li key={conversation.id} className="flex items-stretch gap-1">
              <button
                type="button"
                onClick={() => onSelect(conversation)}
                className="flex-1 rounded-lg border border-neutral-200 px-3 py-2 text-left hover:bg-neutral-50"
              >
                <p className="truncate text-sm font-medium text-neutral-900">{conversation.title}</p>
                <p className="text-xs text-neutral-400">{formatRelativeTime(conversation.updatedAt)}</p>
              </button>
              <button
                type="button"
                onClick={() => onDelete(conversation)}
                aria-label={`Delete conversation "${conversation.title}"`}
                title="Delete conversation"
                className="rounded-lg border border-neutral-200 px-2 text-xs text-neutral-400 hover:border-red-200 hover:bg-red-50 hover:text-red-600"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function MessageBubble({
  message,
  onEdit,
  editDisabled,
}: {
  message: DisplayMessage;
  onEdit?: () => void;
  editDisabled?: boolean;
}) {
  const isUser = message.role === "user";
  const uniqueSources = message.sources
    ? Array.from(new Map(message.sources.map((s) => [`${s.title}-${s.url ?? s.page}`, s])).values())
    : [];

  return (
    <div className={`flex flex-col ${isUser ? "items-end" : "items-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm ${
          isUser ? "bg-neutral-900 text-white" : "bg-neutral-100 text-neutral-900"
        }`}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        {uniqueSources.length > 0 && (
          <div className="mt-2 border-t border-neutral-300/50 pt-2 text-xs">
            <p className="font-medium">Sources:</p>
            <ul className="mt-1 list-inside list-disc">
              {uniqueSources.map((s) => (
                <li key={`${s.title}-${s.url ?? s.page}`}>
                  {s.doc_type === "pdf" ? (
                    <span>
                      {s.title} {s.page ? `(p. ${s.page})` : ""}
                    </span>
                  ) : s.url ? (
                    <a href={s.url} target="_blank" rel="noreferrer" className="underline underline-offset-2">
                      {s.title}
                    </a>
                  ) : (
                    <span>{s.title}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      {onEdit && (
        <button
          type="button"
          onClick={onEdit}
          disabled={editDisabled}
          className="mt-1 text-[11px] text-neutral-400 hover:text-neutral-600 hover:underline disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:no-underline"
        >
          Edit
        </button>
      )}
    </div>
  );
}
