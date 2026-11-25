"use client";

import React from "react";
import { Users, CheckCircle2, ShieldAlert, AlertTriangle, Clock } from "lucide-react";
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
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-3.5">
      {/* Total Employees */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
        <div className="flex items-center justify-between text-slate-500 mb-1.5">
          <span className="text-[11px] font-semibold uppercase tracking-wider">Total Employees</span>
          <span className="p-1.5 rounded-lg bg-indigo-50 text-indigo-600">
            <Users className="w-4 h-4" />
          </span>
        </div>
        <div className="text-2xl font-bold text-slate-900 tabular-nums">{totalEmployees}</div>
        <div className="text-xs text-slate-500 mt-1">Active operational headcount</div>
      </div>

      {/* Coverage % */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
        <div className="flex items-center justify-between text-slate-500 mb-1.5">
          <span className="text-[11px] font-semibold uppercase tracking-wider">Coverage Rate</span>
          <span className="p-1.5 rounded-lg bg-emerald-50 text-emerald-600">
            <CheckCircle2 className="w-4 h-4" />
          </span>
        </div>
        <div className="flex items-baseline justify-between">
          <span className="text-2xl font-bold text-slate-900 tabular-nums">
            {kpis ? `${coveragePct.toFixed(1)}%` : "—"}
          </span>
          {kpis && (
            <span className="text-xs text-slate-500 tabular-nums">
              {coveredSlots}/{totalSlots} slots
            </span>
          )}
        </div>
        <div className="w-full h-1.5 bg-slate-100 rounded-full mt-2.5 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              coveragePct >= 95
                ? "bg-emerald-500"
                : coveragePct >= 80
                ? "bg-amber-500"
                : "bg-rose-500"
            }`}
            style={{ width: `${Math.min(100, Math.max(0, coveragePct))}%` }}
          />
        </div>
      </div>

      {/* Active Hard Conflicts */}
      <button
        type="button"
        onClick={() => onOpenConflicts("HARD")}
        className={`text-left bg-white border rounded-xl p-4 shadow-sm transition-colors hover:border-rose-300 ${
          hardCount > 0 ? "border-rose-200 bg-rose-50/30" : "border-slate-200"
        }`}
      >
        <div className="flex items-center justify-between text-slate-500 mb-1.5">
          <span className="text-[11px] font-semibold uppercase tracking-wider">Hard Conflicts</span>
          <span className="p-1.5 rounded-lg bg-rose-50 text-rose-600">
            <ShieldAlert className="w-4 h-4" />
          </span>
        </div>
        <div
          className={`text-2xl font-bold tabular-nums ${
            hardCount > 0 ? "text-rose-600" : "text-slate-900"
          }`}
        >
          {kpis ? hardCount : "—"}
        </div>
        <div className="text-xs text-rose-600 font-medium mt-1">
          {hardCount > 0 ? "Click to resolve gaps →" : "All required slots covered"}
        </div>
      </button>

      {/* Soft Warnings */}
      <button
        type="button"
        onClick={() => onOpenConflicts("SOFT")}
        className="text-left bg-white border border-slate-200 rounded-xl p-4 shadow-sm transition-colors hover:border-amber-300"
      >
        <div className="flex items-center justify-between text-slate-500 mb-1.5">
          <span className="text-[11px] font-semibold uppercase tracking-wider">Soft Warnings</span>
          <span className="p-1.5 rounded-lg bg-amber-50 text-amber-600">
            <AlertTriangle className="w-4 h-4" />
          </span>
        </div>
        <div
          className={`text-2xl font-bold tabular-nums ${
            softCount > 0 ? "text-amber-600" : "text-slate-900"
          }`}
        >
          {kpis ? softCount : "—"}
        </div>
        <div className="text-xs text-slate-500 mt-1">
          {softCount > 0 ? "Weekly-off preference overrides" : "No preference overrides"}
        </div>
      </button>

      {/* Pending Leaves */}
      <button
        type="button"
        onClick={onJumpToLeaves}
        className={`text-left bg-white border rounded-xl p-4 shadow-sm transition-colors hover:border-indigo-300 col-span-2 lg:col-span-1 ${
          pendingLeavesCount > 0 ? "border-amber-300 bg-amber-50/30" : "border-slate-200"
        }`}
      >
        <div className="flex items-center justify-between text-slate-500 mb-1.5">
          <span className="text-[11px] font-semibold uppercase tracking-wider">Pending Leaves</span>
          <span className="p-1.5 rounded-lg bg-amber-50 text-amber-600">
            <Clock className="w-4 h-4" />
          </span>
        </div>
        <div
          className={`text-2xl font-bold tabular-nums ${
            pendingLeavesCount > 0 ? "text-amber-700" : "text-slate-900"
          }`}
        >
          {pendingLeavesCount}
        </div>
        <div className="text-xs text-slate-500 mt-1">
          {pendingLeavesCount > 0 ? "Awaiting approval & impact check" : "Queue clear"}
        </div>
      </button>
    </div>
  );
}
