"use client";

import React, { useMemo, useState } from "react";
import {
  X,
  ShieldAlert,
  AlertTriangle,
  Search,
  UserCheck,
  Loader2,
  CheckCircle2,
  Sparkles,
  Zap,
} from "lucide-react";
import {
  AutoResolveResponse,
  Conflict,
  ExplainConflictResponse,
  MonthlyRosterResponse,
  SuggestedResolution,
  assignBackup,
  autoResolveGaps,
  explainConflict,
} from "@/lib/api";

interface ConflictDrawerProps {
  open: boolean;
  onClose: () => void;
  month: string;
  conflicts: Conflict[];
  initialSeverity?: "ALL" | "HARD" | "SOFT";
  onRosterUpdated: (roster: MonthlyRosterResponse) => void;
}

export default function ConflictDrawer({
  open,
  onClose,
  month,
  conflicts,
  initialSeverity = "ALL",
  onRosterUpdated,
}: ConflictDrawerProps) {
  const [severityFilter, setSeverityFilter] = useState<"ALL" | "HARD" | "SOFT">(initialSeverity);
  const [searchQuery, setSearchQuery] = useState("");
  const [assigningKey, setAssigningKey] = useState<string | null>(null);
  const [autoResolving, setAutoResolving] = useState(false);
  const [autoResolveResult, setAutoResolveResult] = useState<AutoResolveResponse | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [explainingKey, setExplainingKey] = useState<string | null>(null);
  const [explanations, setExplanations] = useState<Record<string, ExplainConflictResponse>>({});
  const [prevOpen, setPrevOpen] = useState(open);
  const [prevInitialSeverity, setPrevInitialSeverity] = useState(initialSeverity);

  if (open !== prevOpen || initialSeverity !== prevInitialSeverity) {
    setPrevOpen(open);
    setPrevInitialSeverity(initialSeverity);
    if (open) {
      setSeverityFilter(initialSeverity);
    } else {
      setAutoResolveResult(null);
    }
  }

  const hardCount = useMemo(
    () => conflicts.filter((c) => c.severity === "HARD").length,
    [conflicts]
  );
  const softCount = useMemo(
    () => conflicts.filter((c) => c.severity === "SOFT").length,
    [conflicts]
  );

  const filteredConflicts = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return conflicts.filter((c) => {
      if (severityFilter !== "ALL" && c.severity !== severityFilter) return false;
      if (!q) return true;
      return (
        c.message.toLowerCase().includes(q) ||
        (c.conflict_type || "").toLowerCase().replace(/_/g, " ").includes(q) ||
        (c.conflict_type || "").toLowerCase().includes(q) ||
        (c.brand_id || "").toLowerCase().includes(q) ||
        (c.brand_name || "").toLowerCase().includes(q) ||
        (c.process_id || "").toLowerCase().includes(q) ||
        (c.process_name || "").toLowerCase().includes(q) ||
        (c.employee_id || "").toLowerCase().includes(q) ||
        (c.employee_name || "").toLowerCase().includes(q) ||
        c.date.includes(q)
      );
    });
  }, [conflicts, severityFilter, searchQuery]);

  if (!open) return null;

  const handleAssignBackup = async (conflict: Conflict, candidate: SuggestedResolution) => {
    if (!conflict.brand_id || !conflict.process_id) {
      setErrorMsg("Cannot assign backup: conflict is missing brand_id or process_id.");
      return;
    }
    const key = `${conflict.date}|${conflict.brand_id}|${conflict.process_id}|${candidate.employee_id}`;
    try {
      setAssigningKey(key);
      setErrorMsg(null);
      setFeedback(null);
      const updated = await assignBackup(month, {
        date: conflict.date,
        brand_id: conflict.brand_id,
        process_id: conflict.process_id,
        employee_id: candidate.employee_id,
        notes: `1-click backup resolution (${candidate.tier}, score ${candidate.score})`,
      });
      onRosterUpdated(updated);
      setFeedback(
        `Assigned ${candidate.name} (${candidate.employee_id}) as backup for ${
          conflict.brand_name || conflict.brand_id
        } on ${conflict.date}.`
      );
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to assign backup");
    } finally {
      setAssigningKey(null);
    }
  };

  const handleAutoResolve = async () => {
    try {
      setAutoResolving(true);
      setErrorMsg(null);
      setFeedback(null);
      setAutoResolveResult(null);
      const res = await autoResolveGaps(month, 70);
      onRosterUpdated(res.roster);
      setAutoResolveResult(res);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to auto-resolve gaps");
    } finally {
      setAutoResolving(false);
    }
  };

  const handleExplainConflict = async (conflict: Conflict, cardKey: string) => {
    try {
      setExplainingKey(cardKey);
      setErrorMsg(null);
      const res = await explainConflict(month, conflict);
      setExplanations((prev) => ({ ...prev, [cardKey]: res }));
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to generate AI explanation");
    } finally {
      setExplainingKey(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-neutral-950/25 backdrop-blur-[2px] transition-opacity"
        onClick={onClose}
      />

      {/* Drawer Panel */}
      <aside className="relative z-10 w-full max-w-2xl bg-neutral-50 border-l border-neutral-200 shadow-2xl flex flex-col h-full">
        {/* Header */}
        <div className="bg-white border-b border-neutral-200 px-6 py-4 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-lg font-bold tracking-tight text-neutral-950">
              Conflict &amp; Resolution Center
            </h2>
            <p className="text-xs text-neutral-500 mt-0.5">
              {hardCount} Hard Conflicts (coverage gaps) &middot; {softCount} Soft Warnings (off preferences)
            </p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              type="button"
              disabled={hardCount === 0 || autoResolving}
              onClick={handleAutoResolve}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-teal-600 hover:bg-teal-700 text-white text-xs font-semibold shadow-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
            >
              {autoResolving ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Zap className="w-3.5 h-3.5" />
              )}
              {autoResolving ? "Auto-Resolving..." : "Auto-Resolve Solvable Gaps (Score ≥ 70)"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-2 rounded-full text-neutral-500 hover:text-neutral-950 hover:bg-neutral-100 transition-colors"
              aria-label="Close Conflict Drawer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="bg-white border-b border-neutral-200 px-6 py-3 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2.5">
          <div className="flex items-center gap-1.5">
            {(["ALL", "HARD", "SOFT"] as const).map((sev) => (
              <button
                key={sev}
                type="button"
                onClick={() => setSeverityFilter(sev)}
                className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-colors ${
                  severityFilter === sev
                    ? sev === "HARD"
                      ? "bg-red-600 text-white"
                      : sev === "SOFT"
                      ? "bg-amber-500 text-white"
                      : "bg-neutral-900 text-white"
                    : "bg-neutral-100 text-neutral-600 hover:bg-neutral-200"
                }`}
              >
                {sev === "ALL"
                  ? `All (${conflicts.length})`
                  : sev === "HARD"
                  ? `Hard (${hardCount})`
                  : `Soft (${softCount})`}
              </button>
            ))}
          </div>

          <div className="relative flex-1 sm:max-w-xs">
            <Search className="w-3.5 h-3.5 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter brand, employee, date..."
              className="w-full pl-8 pr-3 py-1.5 text-xs bg-neutral-50 border border-neutral-200 rounded-full text-neutral-900 placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-neutral-900/15"
            />
          </div>
        </div>

        {/* Feedback / Errors / Auto-Resolve Banner */}
        {(feedback || errorMsg || autoResolveResult) && (
          <div className="px-5 pt-3 space-y-2">
            {autoResolveResult && (
              <div className="bg-teal-50 border border-teal-200 text-teal-900 px-3.5 py-2.5 rounded-lg text-xs space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 font-semibold">
                    <CheckCircle2 className="w-4 h-4 text-teal-600 flex-shrink-0" />
                    <span>
                      Resolved {autoResolveResult.resolved_count}{" "}
                      {autoResolveResult.resolved_count === 1 ? "gap" : "gaps"} &bull; Coverage
                      jumped from{" "}
                      <span className="tabular-nums">
                        {autoResolveResult.coverage_before.toFixed(1)}%
                      </span>{" "}
                      &rarr;{" "}
                      <span className="tabular-nums">
                        {autoResolveResult.coverage_after.toFixed(1)}%
                      </span>
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setAutoResolveResult(null)}
                    className="text-teal-600 hover:text-teal-900 p-0.5 rounded transition-colors"
                    aria-label="Dismiss auto-resolve banner"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
                {autoResolveResult.remaining_hard_conflicts > 0 &&
                  autoResolveResult.structural_gaps_summary && (
                    <p className="text-[11px] text-amber-900 bg-amber-50 border border-amber-200 rounded px-2.5 py-1.5 leading-relaxed">
                      {autoResolveResult.structural_gaps_summary}
                    </p>
                  )}
              </div>
            )}
            {feedback && (
              <div className="flex items-center gap-2 bg-emerald-50 border border-emerald-200 text-emerald-800 px-3.5 py-2 rounded-lg text-xs font-medium">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                <span>{typeof feedback === "string" ? feedback : JSON.stringify(feedback)}</span>
              </div>
            )}
            {errorMsg && (
              <div className="bg-rose-50 border border-rose-200 text-rose-800 px-3.5 py-2 rounded-lg text-xs font-medium">
                {typeof errorMsg === "string" ? errorMsg : JSON.stringify(errorMsg)}
              </div>
            )}
          </div>
        )}

        {/* Conflict List */}
        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          {filteredConflicts.length === 0 ? (
            <div className="bg-white border border-neutral-200 rounded-xl p-8 text-center">
              <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
              <p className="text-sm font-semibold text-slate-900">No matching conflicts</p>
              <p className="text-xs text-slate-500 mt-1">
                All operational slots matching your filter are clean.
              </p>
            </div>
          ) : (
            filteredConflicts.map((conf, idx) => {
              const isHard = conf.severity === "HARD";
              const isStructuralGap =
                isHard &&
                (!conf.suggested_resolutions ||
                  conf.suggested_resolutions.length === 0 ||
                  !conf.suggested_resolutions.some((cand) => cand.score >= 70));
              const cardKey = `${conf.date}-${conf.conflict_type}-${conf.brand_id}-${conf.process_id}-${conf.employee_id}-${idx}`;
              const explanation = explanations[cardKey];
              const isExplaining = explainingKey === cardKey;
              return (
                <div
                  key={cardKey}
                  className={`bg-white border rounded-xl p-4 shadow-sm ${
                    isHard ? "border-rose-200" : "border-amber-200"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold ${
                          isHard
                            ? "bg-rose-100 text-rose-800"
                            : "bg-amber-100 text-amber-800"
                        }`}
                      >
                        {isHard ? (
                          <ShieldAlert className="w-3 h-3" />
                        ) : (
                          <AlertTriangle className="w-3 h-3" />
                        )}
                        {conf.severity}
                      </span>
                      <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                        {conf.conflict_type.replace(/_/g, " ")}
                      </span>
                      {isStructuralGap && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-800 border border-amber-200">
                          Structural Gap (Extra Headcount Needed)
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        disabled={isExplaining}
                        onClick={() => handleExplainConflict(conf, cardKey)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 text-indigo-700 text-[11px] font-semibold transition-colors disabled:opacity-50"
                      >
                        {isExplaining ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <Sparkles className="w-3 h-3" />
                        )}
                        AI Explain
                      </button>
                      <span className="text-xs font-mono font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-700 tabular-nums">
                        {conf.date}
                      </span>
                    </div>
                  </div>

                  {/* Tags */}
                  <div className="flex flex-wrap items-center gap-1.5 mt-2">
                    {conf.brand_id && (
                      <span className="text-[11px] px-2 py-0.5 rounded bg-neutral-100 text-neutral-800 font-medium">
                        {conf.brand_name ? `${conf.brand_name} (${conf.brand_id})` : conf.brand_id}
                      </span>
                    )}
                    {conf.process_id && (
                      <span className="text-[11px] px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-medium">
                        {conf.process_name || conf.process_id}
                      </span>
                    )}
                    {conf.employee_id && (
                      <span className="text-[11px] px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-medium">
                        {conf.employee_name
                          ? `${conf.employee_name} (${conf.employee_id})`
                          : conf.employee_id}
                      </span>
                    )}
                  </div>

                  <p className="mt-2.5 text-sm text-slate-800 leading-relaxed">{conf.message}</p>

                  {/* AI Explanation Panel */}
                  {explanation && (
                    <div className="mt-3 rounded-xl bg-indigo-50/70 border border-indigo-200 p-3 space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="inline-flex items-center gap-1 text-[11px] font-bold text-indigo-900">
                          <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                          AI Root-Cause &amp; Resolution
                        </span>
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-white border border-indigo-200 text-indigo-700">
                          {explanation.provider}
                        </span>
                      </div>
                      <p className="text-xs text-slate-800 leading-relaxed">
                        {explanation.explanation}
                      </p>
                      {explanation.action_steps && explanation.action_steps.length > 0 && (
                        <ul className="list-disc pl-4 space-y-1 text-[11px] text-slate-700">
                          {explanation.action_steps.map((step, sIdx) => (
                            <li key={sIdx}>{step}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}

                  {/* Recommended Backups */}
                  {conf.suggested_resolutions && conf.suggested_resolutions.length > 0 && (
                    <div className="mt-3.5 pt-3 border-t border-neutral-100">
                      <div className="text-[11px] font-semibold uppercase tracking-wider text-neutral-900 mb-2">
                        Resolve with Recommended Backup
                      </div>
                      <div className="space-y-2">
                        {conf.suggested_resolutions.map((cand) => {
                          const key = `${conf.date}|${conf.brand_id}|${conf.process_id}|${cand.employee_id}`;
                          const isAssigning = assigningKey === key;
                          return (
                            <div
                              key={cand.employee_id}
                              className="flex items-center justify-between gap-3 bg-neutral-50 border border-neutral-200 rounded-lg p-2.5"
                            >
                              <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-1.5">
                                  <span className="text-xs font-semibold text-slate-900">
                                    {cand.name}
                                  </span>
                                  <span className="text-[11px] font-mono text-slate-500">
                                    {cand.employee_id}
                                  </span>
                                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-neutral-200 text-neutral-800 tabular-nums">
                                    Score {cand.score}
                                  </span>
                                  <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-slate-200 text-slate-700">
                                    {cand.tier.replace(/_/g, " ")}
                                  </span>
                                </div>
                                <p className="text-[11px] text-slate-600 mt-0.5 truncate">
                                  {cand.reason}
                                </p>
                              </div>

                              {conf.brand_id && conf.process_id && (
                                <button
                                  type="button"
                                  disabled={isAssigning}
                                  onClick={() => handleAssignBackup(conf, cand)}
                                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-teal-600 hover:bg-teal-700 text-white text-xs font-semibold flex-shrink-0 disabled:opacity-50"
                                >
                                  {isAssigning ? (
                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                  ) : (
                                    <UserCheck className="w-3.5 h-3.5" />
                                  )}
                                  Assign Backup
                                </button>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </aside>
    </div>
  );
}
