"use client";

import React from "react";
import { Users, CheckCircle2, ShieldAlert, AlertTriangle, Clock, ArrowUpRight } from "lucide-react";
import { KPIStats } from "@/lib/api";

interface KpiBarProps {
  kpis: KPIStats | null;
  totalEmployeesFallback: number;
  pendingLeavesCount: number;
  onOpenConflicts: (severity?: "ALL" | "HARD" | "SOFT") => void;
  onJumpToLeaves?: () => void;
}

export default function KpiBar({
  kpis,
  totalEmployeesFallback,
  pendingLeavesCount,
  onOpenConflicts,
  onJumpToLeaves,
}: KpiBarProps) {
  const totalEmployees = kpis?.total_employees ?? totalEmployeesFallback;
  const coveragePct = kpis?.coverage_percentage ?? 0;
  const coveredSlots = kpis?.covered_slots ?? 0;
  const totalSlots = kpis?.total_operating_slots ?? 0;
  const hardCount = kpis?.hard_conflicts_count ?? 0;
  const softCount = kpis?.soft_conflicts_count ?? 0;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
      {/* Total Employees */}
      <div className="bg-white border border-neutral-200 rounded-2xl p-4 transition-colors hover:border-blue-200">
        <div className="flex items-center justify-between text-neutral-500 mb-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider">Team Headcount</span>
          <span className="p-1.5 rounded-lg bg-blue-50 text-blue-600">
            <Users className="w-3.5 h-3.5" />
          </span>
        </div>
        <div className="text-2xl font-bold tracking-tight text-neutral-950 tabular-nums">
          {totalEmployees}
        </div>
        <div className="text-xs text-neutral-500 mt-1">Active across 4 pods</div>
      </div>

      {/* Coverage % */}
      <div className="bg-white border border-neutral-200 rounded-2xl p-4 transition-colors hover:border-neutral-300">
        <div className="flex items-center justify-between text-neutral-500 mb-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider">Coverage Rate</span>
          <span className="p-1.5 rounded-lg bg-emerald-50 text-emerald-600">
            <CheckCircle2 className="w-3.5 h-3.5" />
          </span>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-2xl font-bold tracking-tight text-neutral-950 tabular-nums">
            {kpis ? `${coveragePct.toFixed(1)}%` : "—"}
          </span>
          {kpis && (
            <span className="text-[11px] font-medium text-neutral-500 tabular-nums">
              {coveredSlots}/{totalSlots} slots
            </span>
          )}
        </div>
        <div className="w-full h-1.5 bg-neutral-100 rounded-full mt-2.5 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              coveragePct >= 95
                ? "bg-emerald-500"
                : coveragePct >= 80
                ? "bg-amber-500"
                : "bg-red-500"
            }`}
            style={{ width: `${Math.min(100, Math.max(0, coveragePct))}%` }}
          />
        </div>
      </div>

      {/* Active Hard Conflicts */}
      <button
        type="button"
        onClick={() => onOpenConflicts("HARD")}
        className={`group text-left border rounded-2xl p-4 transition-all ${
          hardCount > 0
            ? "border-red-200 bg-red-50/40 hover:border-red-300 hover:bg-red-50/70"
            : "border-neutral-200 bg-white hover:border-neutral-300"
        }`}
      >
        <div className="flex items-center justify-between text-neutral-500 mb-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider">Hard Conflicts</span>
          <span className={`p-1.5 rounded-lg ${hardCount > 0 ? "bg-red-100 text-red-600" : "bg-neutral-100 text-neutral-600"}`}>
            <ShieldAlert className="w-3.5 h-3.5" />
          </span>
        </div>
        <div
          className={`text-2xl font-bold tracking-tight tabular-nums ${
            hardCount > 0 ? "text-red-600" : "text-neutral-950"
          }`}
        >
          {kpis ? hardCount : "—"}
        </div>
        <div className={`text-xs font-medium mt-1 inline-flex items-center gap-1 ${hardCount > 0 ? "text-red-600" : "text-neutral-500"}`}>
          {hardCount > 0 ? (
            <>
              Resolve gaps
              <ArrowUpRight className="w-3 h-3 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
            </>
          ) : (
            "All required slots covered"
          )}
        </div>
      </button>

      {/* Soft Warnings */}
      <button
        type="button"
        onClick={() => onOpenConflicts("SOFT")}
        className="group text-left bg-white border border-neutral-200 rounded-2xl p-4 transition-colors hover:border-amber-300"
      >
        <div className="flex items-center justify-between text-neutral-500 mb-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider">Soft Warnings</span>
          <span className="p-1.5 rounded-lg bg-amber-50 text-amber-600">
            <AlertTriangle className="w-3.5 h-3.5" />
          </span>
        </div>
        <div
          className={`text-2xl font-bold tracking-tight tabular-nums ${
            softCount > 0 ? "text-amber-600" : "text-neutral-950"
          }`}
        >
          {kpis ? softCount : "—"}
        </div>
        <div className="text-xs text-neutral-500 mt-1">
          {softCount > 0 ? "Weekly-off preferences shifted" : "No preferences overridden"}
        </div>
      </button>

      {/* Pending Leaves */}
      <button
        type="button"
        onClick={onJumpToLeaves}
        className={`text-left border rounded-2xl p-4 transition-colors ${
          pendingLeavesCount > 0
            ? "border-amber-200 bg-amber-50/40 hover:border-amber-300"
            : "border-neutral-200 bg-white hover:border-neutral-300"
        }`}
      >
        <div className="flex items-center justify-between text-neutral-500 mb-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider">Pending Leaves</span>
          <span className={`p-1.5 rounded-lg ${pendingLeavesCount > 0 ? "bg-amber-100 text-amber-700" : "bg-neutral-100 text-neutral-600"}`}>
            <Clock className="w-3.5 h-3.5" />
          </span>
        </div>
        <div
          className={`text-2xl font-bold tracking-tight tabular-nums ${
            pendingLeavesCount > 0 ? "text-amber-700" : "text-neutral-950"
          }`}
        >
          {pendingLeavesCount}
        </div>
        <div className="text-xs text-neutral-500 mt-1">
          {pendingLeavesCount > 0 ? "Needs manager review" : "All requests processed"}
        </div>
      </button>
    </div>
  );
}
