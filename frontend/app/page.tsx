"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ChatMessage,
  LivePage,
  Source,
  getProgramOptions,
  getProgramTypes,
  scrapeSelection,
  sendChat,
} from "@/lib/api";

interface DisplayMessage extends ChatMessage {
  sources?: Source[];
}

export default function Home() {
  // Program/country selection state
  const [programTypes, setProgramTypes] = useState<Record<string, string> | null>(null);
  const [programTypeLabel, setProgramTypeLabel] = useState<string>("");

  const [programOptions, setProgramOptions] = useState<[string, string][]>([]);
  const [countryOptions, setCountryOptions] = useState<[string, string][]>([]);
  const [programLabel, setProgramLabel] = useState<string>("");
  const [countryLabel, setCountryLabel] = useState<string>("");

  const [optionsLoading, setOptionsLoading] = useState(false);
  const [optionsError, setOptionsError] = useState<string | null>(null);

  const [livePage, setLivePage] = useState<LivePage | null>(null);
  const [scraping, setScraping] = useState(false);
  const [scrapeError, setScrapeError] = useState<string | null>(null);
  const [scrapeNotice, setScrapeNotice] = useState<string | null>(null);

  // Chat state
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  const countryLabelByCode = useMemo(
    () => Object.fromEntries(countryOptions.map(([code, label]) => [code, label])),
    [countryOptions]
  );
  const countryCodeByLabel = useMemo(
    () => Object.fromEntries(countryOptions.map(([code, label]) => [label, code])),
    [countryOptions]
  );
  const programTypeSlug = programTypes?.[programTypeLabel] ?? "";

  // 1. Load program types once.
  useEffect(() => {
    getProgramTypes()
      .then((types) => {
        setProgramTypes(types);
        const firstLabel = Object.keys(types)[0];
        if (firstLabel) setProgramTypeLabel(firstLabel);
      })
      .catch((e: Error) => setOptionsError(e.message));
  }, []);

  // 2. Whenever the program type changes, load its program/country options.
  useEffect(() => {
    if (!programTypeSlug) return;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: show a loading state for the duration of this fetch
    setOptionsLoading(true);
    setOptionsError(null);
    getProgramOptions(programTypeSlug)
      .then(({ programs, countries }) => {
        if (cancelled) return;
        setProgramOptions(programs);
        setCountryOptions(countries);
        setProgramLabel(programs[0]?.[1] ?? "");
        setCountryLabel(countries[0]?.[1] ?? "");
      })
      .catch((e: Error) => {
        if (!cancelled) setOptionsError(e.message);
      })
      .finally(() => {
        if (!cancelled) setOptionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [programTypeSlug]);

  async function handleLoadProgramInfo() {
    if (!programTypeLabel || !programLabel || !countryLabel) return;
    setScraping(true);
    setScrapeError(null);
    setScrapeNotice(null);
    try {
      const page = await scrapeSelection({
        program_type_label: programTypeLabel,
        program_type_slug: programTypeSlug,
        program_label: programLabel,
        country_code: countryCodeByLabel[countryLabel],
        country_label_by_code: countryLabelByCode,
      });
      setLivePage(page);
      setScrapeNotice(`Loaded "${page.title}" — saved to the knowledge base for future questions.`);
    } catch (e) {
      setScrapeError(e instanceof Error ? e.message : "Could not scrape that combination.");
    } finally {
      setScraping(false);
    }
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
      const { reply, sources } = await sendChat({
        question: q,
        chat_history: history,
        live_page: livePage,
      });
      setMessages((prev) => [...prev, { role: "assistant", content: reply, sources }]);
    } catch (err) {
      setChatError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-4 py-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          🎓 TU/e Admission &amp; Enrollment Assistant
        </h1>
        <p className="mt-1 text-sm text-neutral-500">
          Ask about admission, tuition, visas, housing, and deadlines.
        </p>
      </header>

      <section className="rounded-xl border border-neutral-200 bg-white p-4 shadow-sm">
        <h2 className="mb-3 text-sm font-medium text-neutral-700">1. Select your program</h2>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Select
            label="Program type"
            value={programTypeLabel}
            onChange={setProgramTypeLabel}
            options={Object.keys(programTypes ?? {})}
            disabled={!programTypes}
          />
          <Select
            label="Program"
            value={programLabel}
            onChange={setProgramLabel}
            options={programOptions.map(([, label]) => label)}
            disabled={optionsLoading || programOptions.length === 0}
          />
          <Select
            label="Country"
            value={countryLabel}
            onChange={setCountryLabel}
            options={countryOptions.map(([, label]) => label)}
            disabled={optionsLoading || countryOptions.length === 0}
          />
        </div>

        {optionsError && <p className="mt-2 text-sm text-red-600">{optionsError}</p>}

        <button
          onClick={handleLoadProgramInfo}
          disabled={scraping || optionsLoading || !programLabel || !countryLabel}
          className="mt-4 rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {scraping ? "Loading program info…" : "Load program info"}
        </button>

        {scrapeError && <p className="mt-2 text-sm text-red-600">{scrapeError}</p>}
        {scrapeNotice && <p className="mt-2 text-sm text-green-700">{scrapeNotice}</p>}

        {livePage ? (
          <details className="mt-3 rounded-lg bg-neutral-50 p-3 text-sm">
            <summary className="cursor-pointer font-medium text-neutral-700">
              Currently loaded: {livePage.title}
            </summary>
            <a
              href={livePage.url}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-block text-blue-600 underline"
            >
              Source
            </a>
            <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-xs text-neutral-600">
              {livePage.body}
            </pre>
          </details>
        ) : (
          <p className="mt-3 text-sm text-neutral-500">
            No program page loaded yet — you can still ask general admission questions below.
          </p>
        )}
      </section>

      <section className="flex flex-1 flex-col rounded-xl border border-neutral-200 bg-white shadow-sm">
        <h2 className="border-b border-neutral-200 px-4 py-3 text-sm font-medium text-neutral-700">
          2. Ask a question
        </h2>

        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
          {messages.length === 0 && (
            <p className="text-sm text-neutral-400">No messages yet — ask something below.</p>
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
            placeholder="Ask about admission, tuition, visas, housing, deadlines..."
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
      </section>
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
  disabled?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-neutral-600">{label}</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-neutral-300 bg-white px-2 py-2 text-sm disabled:opacity-50"
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </label>
  );
}

function MessageBubble({ message }: { message: DisplayMessage }) {
  const isUser = message.role === "user";
  const uniqueSources = message.sources
    ? Array.from(new Map(message.sources.map((s) => [s.url, s])).values())
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
                <li key={s.url}>
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    className="underline underline-offset-2"
                  >
                    {s.title}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
