"use client";

import React, { useState } from "react";
import { CalendarClock, CheckCircle2, Loader2, XCircle, Sparkles, X } from "lucide-react";
import {
  Employee,
  LeaveAndCompOff,
  MonthlyRosterResponse,
  approveLeave,
  rejectLeave,
  fetchMonthlyRoster,
} from "@/lib/api";

interface PendingLeavesBannerProps {
  month: string;
  leaves: LeaveAndCompOff[];
  employees: Employee[];
  currentRoster: MonthlyRosterResponse | null;
  onRosterUpdated: (roster: MonthlyRosterResponse) => void;
  onLeavesUpdated: () => Promise<void>;
  onOpenConflicts: (severity?: "ALL" | "HARD" | "SOFT") => void;
}

export default function PendingLeavesBanner({
  month,
  leaves,
  employees,
  currentRoster,
  onRosterUpdated,
  onLeavesUpdated,
  onOpenConflicts,
}: PendingLeavesBannerProps) {
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [impactToast, setImpactToast] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const pendingLeaves = leaves.filter((l) => l.status === "PENDING");

  if (pendingLeaves.length === 0 && !impactToast) {
    return null;
  }

  const empMap = new Map(employees.map((e) => [e.id, e]));

  const handleApprove = async (leave: LeaveAndCompOff) => {
    try {
      setProcessingId(leave.id);
      setErrorMsg(null);
      const prevHardCount = currentRoster?.kpis?.hard_conflicts_count ?? 0;
      const prevHardKeys = new Set(
        (currentRoster?.conflicts || [])
          .filter((c) => c.severity === "HARD")
          .map((c) => `${c.date}|${c.brand_id}|${c.process_id}|${c.conflict_type}`)
      );

      const res = await approveLeave(leave.id, month);
      let updatedRoster: MonthlyRosterResponse | null = res.roster || null;

      if (!updatedRoster) {
        updatedRoster = await fetchMonthlyRoster(month);
      }

      onRosterUpdated(updatedRoster);
      await onLeavesUpdated();

      // Build human-readable impact summary
      let summary = res.impact_summary;
      if (!summary) {
        const newHardConflicts = (updatedRoster.conflicts || []).filter(
          (c) =>
            c.severity === "HARD" &&
            !prevHardKeys.has(`${c.date}|${c.brand_id}|${c.process_id}|${c.conflict_type}`)
        );
        const delta = updatedRoster.kpis.hard_conflicts_count - prevHardCount;
        const affectedBrands = Array.from(
          new Set(newHardConflicts.map((c) => c.brand_id || c.brand_name).filter(Boolean))
        );
        if (newHardConflicts.length > 0) {
          summary = `Approved ${leave.id} — flagged ${newHardConflicts.length} new hard conflict${
            newHardConflicts.length === 1 ? "" : "s"
          }${affectedBrands.length > 0 ? ` on ${affectedBrands.join(", ")}` : ""}`;
        } else if (delta > 0) {
          summary = `Approved ${leave.id} — flagged ${delta} new hard conflict${delta === 1 ? "" : "s"}`;
        } else {
          summary = `Approved ${leave.id} (${leave.employee_id}) — zero new coverage gaps created.`;
        }
      }

      setImpactToast(summary);
      onOpenConflicts("HARD");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to approve leave";
      setErrorMsg(msg);
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (leave: LeaveAndCompOff) => {
    try {
      setProcessingId(leave.id);
      setErrorMsg(null);
      await rejectLeave(leave.id);
      await onLeavesUpdated();
      setImpactToast(`Rejected leave request ${leave.id} (${leave.employee_id}).`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to reject leave";
      setErrorMsg(msg);
    } finally {
      setProcessingId(null);
    }
  };

  return (
    <div className="space-y-2.5">
      {impactToast && (
        <div className="flex items-center justify-between gap-3 bg-indigo-50 border border-indigo-200 text-indigo-900 px-4 py-3 rounded-xl shadow-sm">
          <div className="flex items-center gap-2.5 text-sm font-medium">
            <Sparkles className="w-4 h-4 text-indigo-600 flex-shrink-0" />
            <span>{impactToast}</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onOpenConflicts("HARD")}
              className="text-xs font-semibold text-indigo-700 hover:text-indigo-900 underline"
            >
              View Conflicts
            </button>
            <button
              type="button"
              onClick={() => setImpactToast(null)}
              className="p-1 rounded hover:bg-indigo-100 text-indigo-600"
              aria-label="Dismiss impact message"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {errorMsg && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 px-4 py-2.5 rounded-xl text-sm">
          {errorMsg}
        </div>
      )}

      {pendingLeaves.length > 0 && (
        <div className="bg-amber-50/80 border border-amber-200 rounded-xl p-4 shadow-sm">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 mb-3">
            <div className="flex items-center gap-2">
              <span className="p-1.5 rounded-lg bg-amber-100 text-amber-700">
                <CalendarClock className="w-4 h-4" />
              </span>
              <div>
                <h3 className="text-sm font-semibold text-slate-900">
                  Pending Leave &amp; Comp-Off Requests ({pendingLeaves.length})
                </h3>
                <p className="text-xs text-slate-600">
                  Approve to run live incremental re-validation against the active roster without rebuilding the month.
                </p>
              </div>
            </div>
          </div>

          <div className="space-y-2">
            {pendingLeaves.map((leave) => {
              const emp = empMap.get(leave.employee_id);
              const isBusy = processingId === leave.id;
              return (
                <div
                  key={leave.id}
                  className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white border border-amber-200/80 rounded-lg px-3.5 py-2.5"
                >
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="px-2 py-0.5 rounded bg-amber-100 text-amber-800 font-mono text-xs font-semibold">
                      {leave.id}
                    </span>
                    <span className="font-semibold text-slate-900">
                      {emp ? emp.name : leave.employee_id}
                    </span>
                    <span className="text-xs text-slate-500 font-mono">({leave.employee_id})</span>
                    <span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-medium">
                      {leave.type.replace(/_/g, " ")}
                    </span>
                    <span className="text-xs font-medium text-slate-700 tabular-nums">
                      {leave.start_date} → {leave.end_date}
                    </span>
                    {leave.reason && (
                      <span className="text-xs text-slate-500 italic">— {leave.reason}</span>
                    )}
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => handleReject(leave)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-medium disabled:opacity-50"
                    >
                      <XCircle className="w-3.5 h-3.5 text-slate-500" />
                      Reject
                    </button>
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => handleApprove(leave)}
                      className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm disabled:opacity-50"
                    >
                      {isBusy ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <CheckCircle2 className="w-3.5 h-3.5" />
                      )}
                      Approve &amp; Check Impact
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
