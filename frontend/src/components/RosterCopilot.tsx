"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Building2, Loader2, MessageSquare, Send, User, X } from "lucide-react";
import { AssistantChatMessage, Brand, Employee, sendAssistantChat } from "@/lib/api";
import SmartRosterLogo from "@/components/SmartRosterLogo";

interface CopilotEntry extends AssistantChatMessage {
  id: string;
  source?: "ai" | "deterministic_fallback";
}

interface RosterCopilotProps {
  month: string;
  employees: Employee[];
  brands: Brand[];
}

interface TagSuggestion {
  id: string;
  label: string;
  sublabel: string;
  insertText: string;
  kind: "employee" | "brand";
}

const STARTER_PROMPTS = [
  "Which brands have gaps on Dec 25 (Christmas)?",
  "Who can cover for Kabir Verma on Dec 10–11?",
  "Why does Pod 1 have the most conflicts this month?",
  "Which employees have the fewest Sunday offs?",
];

function renderInlineMarkdown(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, idx) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      const inner = part.slice(2, -2).replace(/`([^`]+)`/g, "$1");
      return (
        <strong key={idx} className="font-semibold text-neutral-950">
          {inner}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code
          key={idx}
          className="px-1 py-0.5 rounded bg-neutral-100 text-neutral-800 font-mono text-[11px]"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return <React.Fragment key={idx}>{part}</React.Fragment>;
  });
}

function FormattedMessage({ content }: { content: string }) {
  const lines = content.split("\n");
  return (
    <div className="space-y-1">
      {lines.map((line, idx) => {
        const trimmed = line.trimStart();
        if (trimmed.startsWith("- ")) {
          const indent = line.length - trimmed.length;
          return (
            <div
              key={idx}
              className={`flex items-start gap-1.5 ${indent >= 2 ? "pl-3" : ""}`}
            >
              <span className="text-neutral-400 select-none mt-[1px]">•</span>
              <span className="flex-1">{renderInlineMarkdown(trimmed.slice(2))}</span>
            </div>
          );
        }
        return <div key={idx}>{renderInlineMarkdown(line)}</div>;
      })}
    </div>
  );
}

export default function RosterCopilot({
  month,
  employees,
  brands,
}: RosterCopilotProps) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [messages, setMessages] = useState<CopilotEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const msgCounterRef = useRef(0);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, sending, open]);

  // Detect active @employee or /brand trigger at the end of the input (or before cursor)
  const activeTrigger = useMemo(() => {
    const match = input.match(/(?:^|\s)([@/])([^\s@/]*)$/);
    if (!match) return null;
    const triggerChar = match[1] as "@" | "/";
    const query = match[2].toLowerCase();
    const triggerStart = input.lastIndexOf(triggerChar);
    return { triggerChar, query, triggerStart };
  }, [input]);

  const suggestions: TagSuggestion[] = useMemo(() => {
    if (!activeTrigger) return [];
    const { triggerChar, query } = activeTrigger;
    if (triggerChar === "@") {
      return employees
        .filter(
          (e) =>
            !query ||
            e.name.toLowerCase().includes(query) ||
            e.id.toLowerCase().includes(query)
        )
        .slice(0, 7)
        .map((e) => ({
          id: e.id,
          label: e.name,
          sublabel: `${e.id} · ${e.pod_id}`,
          insertText: `@${e.name} (${e.id}) `,
          kind: "employee",
        }));
    }
    return brands
      .filter(
        (b) =>
          !query ||
          b.name.toLowerCase().includes(query) ||
          b.id.toLowerCase().includes(query)
      )
      .slice(0, 7)
      .map((b) => ({
        id: b.id,
        label: b.name,
        sublabel: `${b.id} · ${b.pod_id}`,
        insertText: `/${b.name} (${b.id}) `,
        kind: "brand",
      }));
  }, [activeTrigger, employees, brands]);

  const applySuggestion = (s: TagSuggestion) => {
    if (!activeTrigger) return;
    const prefix = input.slice(0, activeTrigger.triggerStart);
    setInput(`${prefix}${s.insertText}`);
    setSelectedIdx(0);
    inputRef.current?.focus();
  };

  const handleSend = async (rawText?: string) => {
    const text = (rawText ?? input).trim();
    if (!text || sending) return;

    const historyPayload: AssistantChatMessage[] = messages.map((m) => ({
      role: m.role,
      content: m.content,
    }));

    const userMsg: CopilotEntry = {
      id: `user-${++msgCounterRef.current}`,
      role: "user",
      content: text,
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!rawText) setInput("");
    setError(null);
    setSending(true);

    try {
      const res = await sendAssistantChat(month, text, historyPayload);
      const botMsg: CopilotEntry = {
        id: `bot-${++msgCounterRef.current}`,
        role: "assistant",
        content: res.reply,
        source: res.source,
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Could not reach Roster Copilot."
      );
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed bottom-5 right-5 z-40 flex flex-col items-end">
      {open && (
        <div className="mb-3 w-[360px] sm:w-[420px] max-h-[560px] bg-white border border-neutral-200 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
          {/* Header */}
          <div className="px-4 py-3 border-b border-neutral-200 bg-neutral-50/90 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <SmartRosterLogo size={30} className="rounded-xl shadow-xs" />
              <div>
                <div className="flex items-center gap-1.5">
                  <h3 className="text-xs font-bold text-neutral-900">Roster Copilot</h3>
                  <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-neutral-200/70 text-neutral-700">
                    Read-only
                  </span>
                </div>
                <p className="text-[11px] text-neutral-500">
                  Live grounded Q&amp;A for <span className="font-mono font-semibold">{month}</span>
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-700 hover:bg-neutral-200/60 transition-colors"
              aria-label="Close Roster Copilot"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Messages */}
          <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto p-3.5 space-y-3 min-h-[260px] max-h-[380px] bg-[#FAFAFC]"
          >
            {messages.length === 0 && (
              <div className="space-y-2.5">
                <p className="text-xs text-neutral-600 leading-relaxed">
                  Ask anything about <span className="font-semibold text-neutral-900">{month}</span>{" "}
                  coverage gaps, backup candidates, pod bottlenecks, or use{" "}
                  <code className="px-1 py-0.5 rounded bg-neutral-200/70 font-mono text-[11px]">@</code>{" "}
                  for employees and{" "}
                  <code className="px-1 py-0.5 rounded bg-neutral-200/70 font-mono text-[11px]">/</code>{" "}
                  for brands:
                </p>
                <div className="flex flex-col gap-1.5">
                  {STARTER_PROMPTS.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      disabled={sending}
                      onClick={() => handleSend(prompt)}
                      className="text-left px-3 py-2 rounded-xl bg-white hover:bg-blue-50/60 border border-neutral-200 hover:border-blue-300 text-xs font-medium text-neutral-800 transition-colors"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m) => (
              <div
                key={m.id}
                className={`flex flex-col ${
                  m.role === "user" ? "items-end" : "items-start"
                }`}
              >
                <div
                  className={`max-w-[92%] rounded-2xl px-3.5 py-2.5 text-xs leading-relaxed ${
                    m.role === "user"
                      ? "bg-neutral-900 text-white rounded-br-sm whitespace-pre-wrap"
                      : "bg-white border border-neutral-200 text-neutral-800 rounded-bl-sm shadow-2xs"
                  }`}
                >
                  {m.role === "assistant" ? (
                    <FormattedMessage content={m.content} />
                  ) : (
                    m.content
                  )}
                </div>
                {m.role === "assistant" && m.source && (
                  <span
                    className={`mt-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                      m.source === "ai"
                        ? "bg-indigo-50 text-indigo-700 border-indigo-200"
                        : "bg-neutral-100 text-neutral-600 border-neutral-200"
                    }`}
                  >
                    {m.source === "ai" ? "AI" : "Deterministic"}
                  </span>
                )}
              </div>
            ))}

            {sending && (
              <div className="flex items-center gap-2 text-xs text-neutral-500 pl-1">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-600" />
                <span>Analyzing live {month} roster...</span>
              </div>
            )}

            {error && (
              <div className="bg-rose-50 border border-rose-200 text-rose-700 px-3 py-2 rounded-xl text-xs">
                {error}
              </div>
            )}
          </div>

          {/* @Employee / /Brand Autocomplete Popover */}
          {activeTrigger && suggestions.length > 0 && (
            <div className="border-t border-neutral-200 bg-white max-h-44 overflow-y-auto px-2 py-1.5 space-y-0.5">
              <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-neutral-400">
                {activeTrigger.triggerChar === "@"
                  ? "Tag Employee (@)"
                  : "Tag Brand / Company (/)"}
              </div>
              {suggestions.map((s, idx) => (
                <button
                  key={s.id}
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    applySuggestion(s);
                  }}
                  className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-left text-xs transition-colors ${
                    idx === selectedIdx
                      ? "bg-blue-50 text-blue-900"
                      : "hover:bg-neutral-100 text-neutral-800"
                  }`}
                >
                  <span className="inline-flex items-center gap-2 font-medium truncate">
                    {s.kind === "employee" ? (
                      <User className="w-3.5 h-3.5 text-blue-600 flex-shrink-0" />
                    ) : (
                      <Building2 className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
                    )}
                    <span className="truncate">{s.label}</span>
                  </span>
                  <span className="font-mono text-[10px] text-neutral-500 ml-2 flex-shrink-0">
                    {s.sublabel}
                  </span>
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (activeTrigger && suggestions.length > 0) {
                applySuggestion(suggestions[selectedIdx] || suggestions[0]);
                return;
              }
              handleSend();
            }}
            className="p-2.5 border-t border-neutral-200 bg-white flex items-center gap-2"
          >
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                setSelectedIdx(0);
              }}
              onKeyDown={(e) => {
                if (!activeTrigger || suggestions.length === 0) return;
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setSelectedIdx((prev) => (prev + 1) % suggestions.length);
                } else if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setSelectedIdx((prev) => (prev - 1 + suggestions.length) % suggestions.length);
                } else if (e.key === "Tab") {
                  e.preventDefault();
                  applySuggestion(suggestions[selectedIdx] || suggestions[0]);
                } else if (e.key === "Escape") {
                  e.preventDefault();
                  setInput((prev) => prev.slice(0, activeTrigger.triggerStart));
                }
              }}
              placeholder="Ask about gaps, or type @employee /brand..."
              disabled={sending}
              className="flex-1 px-3 py-2 text-xs bg-neutral-50 border border-neutral-200 rounded-xl focus:outline-none focus:border-blue-500"
            />
            <button
              type="submit"
              disabled={sending || !input.trim()}
              className="inline-flex items-center justify-center p-2 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white transition-colors"
              aria-label="Send message"
            >
              {sending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </button>
          </form>
        </div>
      )}

      {/* Floating Toggle Button */}
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-neutral-900 hover:bg-neutral-800 text-white text-xs font-semibold shadow-lg shadow-neutral-900/20 border border-neutral-700/60 transition-all"
      >
        {open ? (
          <X className="w-4 h-4" />
        ) : (
          <MessageSquare className="w-4 h-4 text-blue-400" />
        )}
        <span>Roster Copilot</span>
      </button>
    </div>
  );
}
