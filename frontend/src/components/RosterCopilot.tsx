"use client";

import React, { useEffect, useRef, useState } from "react";
import { Loader2, MessageSquare, Send, Sparkles, X } from "lucide-react";
import { AssistantChatMessage, sendAssistantChat } from "@/lib/api";

interface CopilotEntry extends AssistantChatMessage {
  id: string;
  source?: "ai" | "deterministic_fallback";
}

interface RosterCopilotProps {
  month: string;
}

const STARTER_PROMPTS = [
  "Which brands have gaps on Dec 25 (Christmas)?",
  "Who can cover for Kabir Verma on Dec 10–11?",
  "Why does Pod 1 have the most conflicts this month?",
  "Which employees have the fewest Sunday offs?",
];

export default function RosterCopilot({ month }: RosterCopilotProps) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [messages, setMessages] = useState<CopilotEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, sending, open]);

  const handleSend = async (rawText?: string) => {
    const text = (rawText ?? input).trim();
    if (!text || sending) return;

    const historyPayload: AssistantChatMessage[] = messages.map((m) => ({
      role: m.role,
      content: m.content,
    }));

    const userMsg: CopilotEntry = {
      id: `user-${Date.now()}`,
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
        id: `bot-${Date.now()}`,
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
        <div className="mb-3 w-[360px] sm:w-[410px] max-h-[540px] bg-white border border-neutral-200 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
          {/* Header */}
          <div className="px-4 py-3 border-b border-neutral-200 bg-neutral-50/90 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="p-1.5 rounded-lg bg-blue-600 text-white shadow-xs">
                <Sparkles className="w-3.5 h-3.5" />
              </span>
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
                  coverage gaps, backup candidates, pod bottlenecks, or Sunday-off fairness:
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
                  className={`max-w-[90%] rounded-2xl px-3.5 py-2.5 text-xs leading-relaxed whitespace-pre-wrap ${
                    m.role === "user"
                      ? "bg-neutral-900 text-white rounded-br-sm"
                      : "bg-white border border-neutral-200 text-neutral-800 rounded-bl-sm shadow-2xs"
                  }`}
                >
                  {m.content}
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

          {/* Input */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="p-2.5 border-t border-neutral-200 bg-white flex items-center gap-2"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={`Ask about ${month} gaps, backups, pods...`}
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
        {!open && <Sparkles className="w-3.5 h-3.5 text-amber-400" />}
      </button>
    </div>
  );
}
