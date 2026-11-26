"use client";

import React, { useState } from "react";
import { AlertCircle, CheckCircle2, Clock, Eye, Loader2, ShieldAlert, X } from "lucide-react";
import {
  Employee,
  LeaveAndCompOff,
  LeaveImpactPreviewResponse,
  MonthlyRosterResponse,
  approveLeave,
  previewLeaveImpact,
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
  const [previewingId, setPreviewingId] = useState<string | null>(null);
  const [openPreviewId, setOpenPreviewId] = useState<string | null>(null);
  const [previewsById, setPreviewsById] = useState<Record<string, LeaveImpactPreviewResponse>>({});
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

  const handlePreview = async (leave: LeaveAndCompOff) => {
    if (openPreviewId === leave.id && previewsById[leave.id]) {
      setOpenPreviewId(null);
      return;
    }
    try {
      setPreviewingId(leave.id);
      setError(null);
      const preview = await previewLeaveImpact(leave.id, month);
      setPreviewsById((prev) => ({ ...prev, [leave.id]: preview }));
      setOpenPreviewId(leave.id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to preview leave impact.");
    } finally {
      setPreviewingId(null);
    }
  };

  const handleApprove = async (leave: LeaveAndCompOff) => {
    try {
      setBusyId(leave.id);
      setError(null);
      const res = await approveLeave(leave.id, month);
      if (openPreviewId === leave.id) {
        setOpenPreviewId(null);
      }
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
      if (openPreviewId === leave.id) {
        setOpenPreviewId(null);
      }
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
        <div className="bg-neutral-50 border border-neutral-200 rounded-2xl p-4 space-y-3">
          <div className="flex items-center gap-3">
            <span className="p-2 rounded-xl bg-amber-100 text-amber-800">
              <Clock className="w-4 h-4" />
            </span>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-neutral-950">
                Pending Leave Request{pendingLeaves.length > 1 ? "s" : ""} ({pendingLeaves.length})
              </span>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 text-amber-800">
                Live Impact Check
              </span>
            </div>
          </div>

          <div className="space-y-3">
            {pendingLeaves.map((leave) => {
              const emp = empMap.get(leave.employee_id);
              const preview = openPreviewId === leave.id ? previewsById[leave.id] : undefined;
              const isBusy = busyId === leave.id;
              const isPreviewing = previewingId === leave.id;

              return (
                <div key={leave.id} className="space-y-2">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-neutral-600">
                      <span className="font-semibold text-neutral-900">
                        {emp ? `${emp.name} (${emp.id})` : leave.employee_id}
                      </span>
                      <span className="font-mono text-[11px] bg-white px-2 py-0.5 rounded-full border border-neutral-200 text-neutral-700">
                        {leave.id} &middot; {leave.start_date} → {leave.end_date}
                      </span>
                      <span className="text-neutral-500">{leave.reason || leave.type}</span>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 flex-shrink-0">
                      <button
                        type="button"
                        disabled={isBusy || isPreviewing}
                        onClick={() => handlePreview(leave)}
                        className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-white hover:bg-neutral-100 disabled:opacity-50 border border-neutral-300 text-neutral-800 text-xs font-semibold transition-colors"
                      >
                        {isPreviewing ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Eye className="w-3.5 h-3.5" />
                        )}
                        {isPreviewing
                          ? "Previewing..."
                          : preview
                          ? "Hide Preview"
                          : "Preview Impact"}
                      </button>
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => handleApprove(leave)}
                        className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-neutral-900 hover:bg-neutral-800 disabled:opacity-50 text-white text-xs font-semibold transition-colors"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        {isBusy ? "Checking Impact..." : `Approve ${leave.id} & Check Impact`}
                      </button>
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => handleReject(leave)}
                        className="px-3.5 py-2 rounded-full bg-white hover:bg-neutral-100 border border-neutral-200 text-neutral-700 text-xs font-medium transition-colors"
                      >
                        Reject
                      </button>
                    </div>
                  </div>

                  {preview && (
                    <div className="bg-white border border-amber-200 rounded-xl p-3.5 shadow-sm space-y-2.5 text-xs">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="inline-flex items-center gap-1.5 font-bold text-neutral-900">
                            <ShieldAlert
                              className={`w-3.5 h-3.5 ${
                                preview.new_hard_conflicts_count > 0
                                  ? "text-rose-600"
                                  : "text-emerald-600"
                              }`}
                            />
                            What-If Impact Preview
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${
                              preview.new_hard_conflicts_count > 0
                                ? "bg-rose-50 text-rose-700 border border-rose-200"
                                : "bg-emerald-50 text-emerald-700 border border-emerald-200"
                            }`}
                          >
                            +{preview.new_hard_conflicts_count} hard conflict
                            {preview.new_hard_conflicts_count === 1 ? "" : "s"} (
                            {preview.hard_conflicts_before} → {preview.hard_conflicts_after})
                          </span>
                          <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-neutral-100 text-neutral-800">
                            Coverage: {preview.coverage_before.toFixed(1)}% →{" "}
                            {preview.coverage_after.toFixed(1)}%
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={() => setOpenPreviewId(null)}
                          className="p-1 text-neutral-400 hover:text-neutral-700"
                          title="Close preview"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-[11px] text-neutral-600">
                        <div>
                          <span className="font-semibold text-neutral-800">Affected Brands: </span>
                          {preview.affected_brands.length > 0
                            ? preview.affected_brands.map((b) => b.brand_name).join(", ")
                            : "None"}
                        </div>
                        <div>
                          <span className="font-semibold text-neutral-800">Affected Processes: </span>
                          {preview.affected_processes.length > 0
                            ? preview.affected_processes.join(", ")
                            : "None"}
                        </div>
                        <div>
                          <span className="font-semibold text-neutral-800">Affected Dates: </span>
                          {preview.affected_dates.length > 0
                            ? preview.affected_dates.join(", ")
                            : "None"}
                        </div>
                      </div>

                      {preview.new_conflicts.length > 0 ? (
                        <div className="space-y-1.5 pt-1 border-t border-neutral-100">
                          <div className="text-[11px] font-semibold text-neutral-700">
                            New Coverage Gaps &amp; Top Backup Candidates ({preview.new_conflicts.length})
                          </div>
                          <div className="space-y-1.5">
                            {preview.new_conflicts.map((c, idx) => {
                              const topBackup = c.suggested_resolutions?.[0];
                              return (
                                <div
                                  key={`${c.date}-${c.brand_id ?? ""}-${c.process_id ?? ""}-${idx}`}
                                  className="bg-neutral-50 border border-neutral-200 rounded-lg px-2.5 py-2 flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 text-[11px]"
                                >
                                  <div className="text-neutral-800">
                                    <span
                                      className={`inline-block px-1.5 py-0.5 rounded font-semibold mr-1.5 ${
                                        c.severity === "HARD"
                                          ? "bg-rose-100 text-rose-700"
                                          : "bg-amber-100 text-amber-800"
                                      }`}
                                    >
                                      {c.severity}
                                    </span>
                                    <span className="font-mono text-neutral-700 mr-1.5">{c.date}</span>
                                    <span className="font-semibold">
                                      {c.brand_name || c.brand_id || "—"}
                                      {c.process_name || c.process_id
                                        ? ` / ${c.process_name || c.process_id}`
                                        : ""}
                                    </span>
                                    <span className="text-neutral-500 ml-1.5">{c.message}</span>
                                  </div>
                                  <div className="text-neutral-700 sm:text-right flex-shrink-0">
                                    {topBackup ? (
                                      <span className="inline-flex items-center gap-1 bg-teal-50 text-teal-800 border border-teal-200 px-2 py-0.5 rounded-full font-medium">
                                        Top Backup: {topBackup.name} ({topBackup.employee_id}) &middot;
                                        Score {topBackup.score}
                                      </span>
                                    ) : (
                                      <span className="text-neutral-400 italic">
                                        No backup candidate available
                                      </span>
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      ) : (
                        <div className="text-[11px] text-emerald-700 font-medium pt-1 border-t border-neutral-100">
                          No new coverage gaps detected if this leave is approved.
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
