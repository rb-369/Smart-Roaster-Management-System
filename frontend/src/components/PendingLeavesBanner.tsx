"use client";

import React, { useState } from "react";
import { AlertCircle, CheckCircle2, Clock, ShieldAlert, X } from "lucide-react";
import {
  Employee,
  LeaveAndCompOff,
  MonthlyRosterResponse,
  approveLeave,
  rejectLeave,
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
  onRosterUpdated,
  onLeavesUpdated,
  onOpenConflicts,
}: PendingLeavesBannerProps) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [impactBanner, setImpactBanner] = useState<{
    message: string;
    newHardCount: number;
    affectedBrands: string[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pendingLeaves = leaves.filter((l) => l.status === "PENDING");
  const empMap = new Map(employees.map((e) => [e.id, e]));

  if (pendingLeaves.length === 0 && !impactBanner && !error) {
    return null;
  }

  const handleApprove = async (leave: LeaveAndCompOff) => {
    try {
      setBusyId(leave.id);
      setError(null);
      const res = await approveLeave(leave.id, month);
      if (res.roster) {
        onRosterUpdated(res.roster);
      }
      await onLeavesUpdated();

      const newConflicts = res.impact?.new_conflicts ?? [];
      const delta = res.impact
        ? res.impact.hard_conflicts_after - res.impact.hard_conflicts_before
        : res.new_hard_conflicts_count ?? 0;
      const brands = res.impact?.affected_brands ?? [];
      setImpactBanner({
        message: `Approved ${leave.id} (${leave.employee_id}) — ${
          newConflicts.length
        } new conflict(s) detected (${delta >= 0 ? `+${delta}` : delta} hard).`,
        newHardCount: newConflicts.filter((c) => c.severity === "HARD").length,
        affectedBrands: brands,
      });

      if (newConflicts.length > 0) {
        onOpenConflicts("HARD");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to approve leave.");
    } finally {
      setBusyId(null);
    }
  };

  const handleReject = async (leave: LeaveAndCompOff) => {
    try {
      setBusyId(leave.id);
      setError(null);
      await rejectLeave(leave.id);
      await onLeavesUpdated();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to reject leave.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-3">
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-2xl text-xs font-medium flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-600" />
            <span>{error}</span>
          </div>
          <button type="button" onClick={() => setError(null)} className="text-red-500 hover:text-red-700">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {impactBanner && (
        <div className="bg-white border border-red-200 px-4 py-3 rounded-2xl flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="p-1.5 rounded-lg bg-red-50 text-red-600">
              <ShieldAlert className="w-4 h-4" />
            </span>
            <div className="text-xs text-neutral-800">
              <span className="font-semibold text-neutral-950">{impactBanner.message}</span>
              {impactBanner.affectedBrands.length > 0 && (
                <span className="ml-2 text-neutral-500">
                  Impacted: {impactBanner.affectedBrands.join(", ")}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onOpenConflicts("HARD")}
              className="px-3 py-1.5 rounded-full bg-neutral-900 hover:bg-neutral-800 text-white text-xs font-semibold transition-colors"
            >
              Resolve in Conflict Drawer
            </button>
            <button
              type="button"
              onClick={() => setImpactBanner(null)}
              className="p-1 text-neutral-400 hover:text-neutral-700"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {pendingLeaves.length > 0 && (
        <div className="bg-neutral-50 border border-neutral-200 rounded-2xl p-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div className="flex items-start gap-3">
              <span className="p-2 rounded-xl bg-amber-100 text-amber-800 mt-0.5">
                <Clock className="w-4 h-4" />
              </span>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-neutral-950">
                    Pending Leave Request{pendingLeaves.length > 1 ? "s" : ""} ({pendingLeaves.length})
                  </span>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 text-amber-800">
                    Live Impact Check
                  </span>
                </div>
                <div className="mt-1.5 space-y-1.5">
                  {pendingLeaves.map((leave) => {
                    const emp = empMap.get(leave.employee_id);
                    return (
                      <div
                        key={leave.id}
                        className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-neutral-600"
                      >
                        <span className="font-semibold text-neutral-900">
                          {emp ? `${emp.name} (${emp.id})` : leave.employee_id}
                        </span>
                        <span className="font-mono text-[11px] bg-white px-2 py-0.5 rounded-full border border-neutral-200 text-neutral-700">
                          {leave.id} &middot; {leave.start_date} → {leave.end_date}
                        </span>
                        <span className="text-neutral-500">{leave.reason || leave.type}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 flex-shrink-0">
              {pendingLeaves.map((leave) => (
                <div key={leave.id} className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={busyId === leave.id}
                    onClick={() => handleApprove(leave)}
                    className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-neutral-900 hover:bg-neutral-800 disabled:opacity-50 text-white text-xs font-semibold transition-colors"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    {busyId === leave.id ? "Checking Impact..." : `Approve ${leave.id} & Check Impact`}
                  </button>
                  <button
                    type="button"
                    disabled={busyId === leave.id}
                    onClick={() => handleReject(leave)}
                    className="px-3.5 py-2 rounded-full bg-white hover:bg-neutral-100 border border-neutral-200 text-neutral-700 text-xs font-medium transition-colors"
                  >
                    Reject
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
