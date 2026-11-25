"use client";

import React, { useEffect, useState } from "react";
import {
  X,
  Loader2,
  CheckCircle2,
  ShieldAlert,
  AlertTriangle,
  Sliders,
  Sparkles,
} from "lucide-react";
import {
  MonthlyRosterResponse,
  PlanComparisonItem,
  PlanStrategy,
  applyPlan,
  comparePlans,
} from "@/lib/api";

interface PlanComparisonModalProps {
  open: boolean;
  onClose: () => void;
  month: string;
  onRosterUpdated: (roster: MonthlyRosterResponse) => void;
}

const STRATEGY_META: Record<
  PlanStrategy,
  { title: string; subtitle: string; badge: string; accentClass: string }
> = {
  COVERAGE_FIRST: {
    title: "Coverage First",
    subtitle: "Maximizes client SLA coverage even if preferred weekly offs are overridden.",
    badge: "Max SLA",
    accentClass: "border-emerald-200 bg-emerald-50/40",
  },
  PREFERENCE_FIRST: {
    title: "Preference First",
    subtitle: "Honors employee preferred weekly offs first; may leave coverage gaps.",
    badge: "Employee First",
    accentClass: "border-sky-200 bg-sky-50/40",
  },
  BALANCED: {
    title: "Balanced",
    subtitle: "Balances SLA coverage with rotational weekly-off fairness across pods.",
    badge: "Recommended",
    accentClass: "border-blue-300 bg-blue-50/40",
  },
};

export default function PlanComparisonModal({
  open,
  onClose,
  month,
  onRosterUpdated,
}: PlanComparisonModalProps) {
  const [loading, setLoading] = useState(false);
  const [applyingStrategy, setApplyingStrategy] = useState<PlanStrategy | null>(null);
  const [plans, setPlans] = useState<PlanComparisonItem[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const load = async () => {
      try {
        setLoading(true);
        setErrorMsg(null);
        const res = await comparePlans(month);
        if (!cancelled) {
          setPlans(res.plans || []);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setErrorMsg(err instanceof Error ? err.message : "Failed to compare plans.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [open, month]);

  if (!open) return null;

  const handleApply = async (strategy: PlanStrategy) => {
    try {
      setApplyingStrategy(strategy);
      setErrorMsg(null);
      const updated = await applyPlan(month, strategy);
      onRosterUpdated(updated);
      onClose();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to apply selected plan.");
    } finally {
      setApplyingStrategy(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-neutral-950/35 backdrop-blur-[2px]">
      <div className="bg-white border border-neutral-200 rounded-2xl shadow-2xl w-full max-w-4xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-neutral-200 flex items-center justify-between bg-white">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-blue-50 border border-blue-200 text-blue-600 flex items-center justify-center">
              <Sliders className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-base font-bold text-neutral-950">
                Compare Roster Strategies ({month})
              </h2>
              <p className="text-xs text-neutral-500">
                Side-by-side trade-off analysis across Coverage, Preferences, and Balanced scheduling
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-full text-neutral-500 hover:text-neutral-950 hover:bg-neutral-100 transition-colors"
            aria-label="Close Plan Comparison"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto space-y-4">
          {errorMsg && (
            <div className="bg-rose-50 border border-rose-200 text-rose-800 px-4 py-2.5 rounded-xl text-xs font-medium">
              {errorMsg}
            </div>
          )}

          {loading ? (
            <div className="py-14 flex flex-col items-center justify-center gap-2 text-xs text-neutral-600">
              <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
              <span>Simulating 3 scheduling strategies for {month}...</span>
            </div>
          ) : plans.length === 0 ? (
            <div className="py-12 text-center text-xs text-neutral-500">
              No strategy comparison data available.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {plans.map((plan) => {
                const meta = STRATEGY_META[plan.strategy] || {
                  title: plan.label || plan.strategy,
                  subtitle: plan.description || "",
                  badge: "Strategy",
                  accentClass: "border-neutral-200 bg-neutral-50/40",
                };
                const isApplying = applyingStrategy === plan.strategy;
                return (
                  <div
                    key={plan.strategy}
                    className={`rounded-2xl border p-5 flex flex-col justify-between gap-4 shadow-xs ${meta.accentClass}`}
                  >
                    <div className="space-y-3">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <h3 className="text-sm font-bold text-neutral-950">
                            {plan.label || meta.title}
                          </h3>
                          <p className="text-[11px] text-neutral-600 mt-1 leading-relaxed">
                            {plan.description || meta.subtitle}
                          </p>
                        </div>
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-white border border-neutral-200 text-neutral-800 whitespace-nowrap">
                          {plan.strategy === "BALANCED" && (
                            <Sparkles className="w-2.5 h-2.5 text-blue-600" />
                          )}
                          {meta.badge}
                        </span>
                      </div>

                      <div className="bg-white border border-neutral-200/80 rounded-xl p-3.5 space-y-2.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-neutral-500 font-medium">Coverage %</span>
                          <span className="text-base font-bold text-neutral-950 tabular-nums">
                            {plan.coverage_percentage.toFixed(1)}%
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-neutral-500 font-medium">Covered Slots</span>
                          <span className="text-xs font-semibold text-neutral-900 tabular-nums">
                            {plan.covered_slots}
                            {plan.total_operating_slots
                              ? ` / ${plan.total_operating_slots}`
                              : ""}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-neutral-500 font-medium inline-flex items-center gap-1">
                            <ShieldAlert className="w-3.5 h-3.5 text-rose-600" />
                            Hard Conflicts
                          </span>
                          <span
                            className={`text-xs font-bold px-2 py-0.5 rounded-full tabular-nums ${
                              plan.hard_conflicts_count > 0
                                ? "bg-rose-600 text-white"
                                : "bg-emerald-100 text-emerald-800"
                            }`}
                          >
                            {plan.hard_conflicts_count}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-neutral-500 font-medium inline-flex items-center gap-1">
                            <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                            Soft Warnings
                          </span>
                          <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 tabular-nums">
                            {plan.soft_conflicts_count}
                          </span>
                        </div>
                      </div>
                    </div>

                    <button
                      type="button"
                      disabled={applyingStrategy !== null}
                      onClick={() => handleApply(plan.strategy)}
                      className="w-full inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl bg-neutral-900 hover:bg-neutral-800 disabled:opacity-50 text-white text-xs font-semibold transition-colors shadow-xs"
                    >
                      {isApplying ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <CheckCircle2 className="w-3.5 h-3.5" />
                      )}
                      {isApplying ? "Applying..." : "Apply This Plan"}
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
