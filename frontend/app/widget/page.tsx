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
 */

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ChatMessage, Source, sendChat } from "@/lib/api";

interface DisplayMessage extends ChatMessage {
  sources?: Source[];
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

  if (!widgetKey) {
    return (
      <div className="flex h-screen items-center justify-center p-4 text-sm text-neutral-500">
        Missing widget key — this page must be opened via the Campus-AI widget loader.
      </div>
    );
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

    try {
      const { reply, sources } = await sendChat(widgetKey as string, {
        question: q,
        chat_history: history,
      });
      setMessages((prev) => [...prev, { role: "assistant", content: reply, sources }]);
    } catch (err) {
      setChatError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex h-screen flex-col bg-white">
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <p className="text-sm text-neutral-400">Ask a question about your university&apos;s documents below.</p>
        )}
        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
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
        <button
          type="submit"
          disabled={sending || !question.trim()}
          className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}

function MessageBubble({ message }: { message: DisplayMessage }) {
  const isUser = message.role === "user";
  const uniqueSources = message.sources
    ? Array.from(new Map(message.sources.map((s) => [`${s.title}-${s.url ?? s.page}`, s])).values())
    : [];

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
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
    </div>
  );
}
