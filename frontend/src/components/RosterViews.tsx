"use client";

import React, { useMemo, useState } from "react";
import {
  Building2,
  Layers,
  Tag,
  GitBranch,
  User,
  X,
  Loader2,
  Check,
  AlertCircle,
  Search,
} from "lucide-react";
import {
  Allocation,
  Brand,
  BrandProcessRule,
  DailyCoverage,
  Employee,
  EmployeeStatusType,
  MonthlyRosterResponse,
  Pod,
  Process,
  PublicHoliday,
  RosterEntry,
  RosterViewType,
  WEEKDAY_LABELS,
  patchRosterEntry,
} from "@/lib/api";

interface RosterViewsProps {
  month: string;
  roster: MonthlyRosterResponse;
  pods: Pod[];
  processes: Process[];
  employees: Employee[];
  brands: Brand[];
  rules: BrandProcessRule[];
  allocations: Allocation[];
  holidays: PublicHoliday[];
  onRosterUpdated: (roster: MonthlyRosterResponse) => void;
}

const STATUS_META: Record<
  EmployeeStatusType,
  { code: string; label: string; badgeClass: string }
> = {
  WORKING: {
    code: "W",
    label: "Working",
    badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100",
  },
  WEEKLY_OFF: {
    code: "WO",
    label: "Weekly Off",
    badgeClass: "bg-slate-100 text-slate-600 border-neutral-200 hover:bg-slate-200",
  },
  PUBLIC_HOLIDAY: {
    code: "PH",
    label: "Public Holiday",
    badgeClass: "bg-sky-50 text-sky-700 border-sky-200 hover:bg-sky-100",
  },
  PLANNED_LEAVE: {
    code: "LV",
    label: "Planned Leave",
    badgeClass: "bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100",
  },
  COMP_OFF: {
    code: "CO",
    label: "Comp-Off",
    badgeClass: "bg-purple-50 text-purple-700 border-purple-200 hover:bg-purple-100",
  },
  BACKUP_COVERAGE: {
    code: "BK",
    label: "Backup Coverage",
    badgeClass: "bg-teal-50 text-teal-800 border-teal-200 hover:bg-teal-100",
  },
};

function getMonthDates(month: string): string[] {
  const [yStr, mStr] = month.split("-");
  const year = Number(yStr) || 2026;
  const mon = Number(mStr) || 12;
  const daysInMonth = new Date(Date.UTC(year, mon, 0)).getUTCDate();
  const dates: string[] = [];
  for (let d = 1; d <= daysInMonth; d++) {
    dates.push(`${String(year).padStart(4, "0")}-${String(mon).padStart(2, "0")}-${String(d).padStart(2, "0")}`);
  }
  return dates;
}

/** Python date.weekday() convention: 0=Mon .. 6=Sun */
function getPythonWeekday(dateStr: string): number {
  const [y, m, d] = dateStr.split("-").map(Number);
  const jsDay = new Date(Date.UTC(y, m - 1, d)).getUTCDay(); // 0=Sun..6=Sat
  return (jsDay + 6) % 7;
}

function renderCoverageBadge(cov?: DailyCoverage) {
  if (!cov || !cov.is_operating || cov.status === "NOT_OPERATING") {
    return (
      <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-400">
        —
      </span>
    );
  }
  const ratio = `${cov.working_count}/${cov.required_staffing}`;
  switch (cov.status) {
    case "COVERED":
      return (
        <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 tabular-nums">
          {ratio}
        </span>
      );
    case "BACKUP_COVERED":
      return (
        <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold bg-teal-50 text-teal-800 border border-teal-200 tabular-nums whitespace-nowrap">
          {ratio} BK
        </span>
      );
    case "UNDERSTAFFED":
      return (
        <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-300 tabular-nums whitespace-nowrap">
          {ratio} SHORT
        </span>
      );
    case "UNCOVERED":
    default:
      return (
        <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-300 tabular-nums whitespace-nowrap">
          {ratio} GAP
        </span>
      );
  }
}

export default function RosterViews({
  month,
  roster,
  pods,
  processes,
  employees,
  brands,
  rules,
  allocations,
  holidays,
  onRosterUpdated,
}: RosterViewsProps) {
  const [activeView, setActiveView] = useState<RosterViewType>("company");
  const [selectedPodId, setSelectedPodId] = useState<string>(pods[0]?.id || "");
  const [selectedBrandId, setSelectedBrandId] = useState<string>("ALL");
  const [selectedProcessId, setSelectedProcessId] = useState<string>(processes[0]?.id || "ALL");
  const [employeeSearch, setEmployeeSearch] = useState("");

  // Cell Override Modal State
  const [editingCell, setEditingCell] = useState<{
    employee: Employee;
    date: string;
    entry?: RosterEntry;
  } | null>(null);
  const [overrideStatus, setOverrideStatus] = useState<EmployeeStatusType>("WORKING");
  const [overrideBrandId, setOverrideBrandId] = useState<string>("");
  const [overrideProcessId, setOverrideProcessId] = useState<string>("");
  const [overrideNotes, setOverrideNotes] = useState<string>("");
  const [savingOverride, setSavingOverride] = useState(false);
  const [overrideError, setOverrideError] = useState<string | null>(null);

  // Ensure default selections remain valid
  React.useEffect(() => {
    if (!selectedPodId && pods.length > 0) setSelectedPodId(pods[0].id);
  }, [pods, selectedPodId]);

  React.useEffect(() => {
    if (selectedProcessId === "ALL" && processes.length > 0) {
      setSelectedProcessId(processes[0].id);
    }
  }, [processes, selectedProcessId]);

  const dates = useMemo(() => getMonthDates(month), [month]);
  const holidayMap = useMemo(
    () => new Map(holidays.map((h) => [h.date, h])),
    [holidays]
  );
  const empMap = useMemo(() => new Map(employees.map((e) => [e.id, e])), [employees]);
  const podMap = useMemo(() => new Map(pods.map((p) => [p.id, p])), [pods]);
  const procMap = useMemo(() => new Map(processes.map((p) => [p.id, p])), [processes]);

  // Index entries by `${employee_id}|${date}`
  const entryMap = useMemo(() => {
    const m = new Map<string, RosterEntry>();
    for (const e of roster.entries) {
      m.set(`${e.employee_id}|${e.date}`, e);
    }
    return m;
  }, [roster.entries]);

  // Index coverage by `${brand_id}|${process_id}|${date}`
  const coverageMap = useMemo(() => {
    const m = new Map<string, DailyCoverage>();
    for (const c of roster.coverage_matrix) {
      m.set(`${c.brand_id}|${c.process_id}|${c.date}`, c);
    }
    return m;
  }, [roster.coverage_matrix]);

  // Daily gap counts across all brands/processes
  const dailyGapCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const d of dates) counts.set(d, 0);
    for (const c of roster.coverage_matrix) {
      if (c.status === "UNCOVERED" || c.status === "UNDERSTAFFED") {
        counts.set(c.date, (counts.get(c.date) || 0) + 1);
      }
    }
    return counts;
  }, [roster.coverage_matrix, dates]);

  const openCellEditor = (employee: Employee, date: string) => {
    const entry = entryMap.get(`${employee.id}|${date}`);
    setEditingCell({ employee, date, entry });
    setOverrideStatus(entry?.status || "WORKING");
    setOverrideBrandId(entry?.assigned_brand_id || "");
    setOverrideProcessId(entry?.assigned_process_id || "");
    setOverrideNotes(entry?.notes || "");
    setOverrideError(null);
  };

  const handleSaveOverride = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingCell) return;
    try {
      setSavingOverride(true);
      setOverrideError(null);
      const updated = await patchRosterEntry(month, {
        employee_id: editingCell.employee.id,
        date: editingCell.date,
        status: overrideStatus,
        assigned_brand_id: overrideBrandId || null,
        assigned_process_id: overrideProcessId || null,
        notes: overrideNotes.trim() || null,
      });
      onRosterUpdated(updated);
      setEditingCell(null);
    } catch (err: unknown) {
      setOverrideError(err instanceof Error ? err.message : "Failed to update cell");
    } finally {
      setSavingOverride(false);
    }
  };

  // Reusable Matrix Table for a list of employees (optionally grouped by Pod)
  const renderEmployeeMatrix = (empList: Employee[], groupByPod: boolean) => {
    const groups: { pod: Pod | null; emps: Employee[] }[] = [];
    if (groupByPod && pods.length > 0) {
      for (const pod of pods) {
        const podEmps = empList.filter((e) => e.pod_id === pod.id);
        if (podEmps.length > 0) groups.push({ pod, emps: podEmps });
      }
      const ungrouped = empList.filter((e) => !podMap.has(e.pod_id));
      if (ungrouped.length > 0) groups.push({ pod: null, emps: ungrouped });
    } else {
      groups.push({ pod: null, emps: empList });
    }

    return (
      <div className="bg-white border border-neutral-200 rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto max-h-[640px]">
          <table className="w-full border-collapse text-xs">
            <thead className="sticky top-0 z-30 bg-neutral-50 border-b border-neutral-200">
              {/* Day Header Row */}
              <tr>
                <th className="sticky left-0 z-40 bg-neutral-50 border-r border-neutral-200 px-3 py-2.5 text-left font-semibold text-slate-700 min-w-[210px]">
                  Employee / Pod
                </th>
                {dates.map((d) => {
                  const dayNum = d.slice(8, 10);
                  const wd = WEEKDAY_LABELS[getPythonWeekday(d)];
                  const isWeekend = wd === "Sat" || wd === "Sun";
                  const ph = holidayMap.get(d);
                  return (
                    <th
                      key={d}
                      title={ph ? `Public Holiday: ${ph.name}` : d}
                      className={`px-1 py-2 text-center font-semibold border-r border-neutral-100 min-w-[38px] tabular-nums ${
                        ph
                          ? "bg-sky-50 text-sky-800"
                          : isWeekend
                          ? "bg-slate-100/70 text-slate-600"
                          : "text-slate-700"
                      }`}
                    >
                      <div className="text-[11px] leading-tight">{dayNum}</div>
                      <div className="text-[9px] font-medium text-slate-400 uppercase">{wd}</div>
                    </th>
                  );
                })}
              </tr>

              {/* Daily Coverage Health Summary Row */}
              <tr className="bg-white border-b-2 border-neutral-300">
                <th className="sticky left-0 z-40 bg-white border-r-2 border-neutral-200 px-3 py-2 text-left text-[11px] font-semibold text-neutral-600 uppercase tracking-wider">
                  Daily Coverage Health
                </th>
                {dates.map((d) => {
                  const gaps = dailyGapCounts.get(d) || 0;
                  return (
                    <th
                      key={`health-${d}`}
                      className="px-1 py-2 text-center border-r border-neutral-200/70 tabular-nums"
                      title={gaps === 0 ? `${d}: All slots covered` : `${d}: ${gaps} coverage gap(s)`}
                    >
                      {gaps === 0 ? (
                        <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-emerald-50 text-emerald-600">
                          <Check className="w-3 h-3" />
                        </span>
                      ) : (
                        <span className="inline-flex items-center justify-center min-w-[20px] h-5 px-1 rounded-full bg-rose-100 text-rose-700 text-[10px] font-bold">
                          {gaps}
                        </span>
                      )}
                    </th>
                  );
                })}
              </tr>
            </thead>

            <tbody className="divide-y divide-neutral-200">
              {groups.map((grp, gIdx) => {
                const podDotColors = ["bg-rose-500", "bg-sky-500", "bg-emerald-500", "bg-amber-500"];
                const podDot = podDotColors[gIdx % podDotColors.length];
                return (
                <React.Fragment key={grp.pod?.id || `grp-${gIdx}`}>
                  {grp.pod && (
                    <tr className="bg-neutral-100/95 border-y-2 border-neutral-300">
                      <td
                        colSpan={dates.length + 1}
                        className="sticky left-0 px-3 py-2 text-[11px] font-bold text-neutral-800 uppercase tracking-wider"
                      >
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${podDot}`} />
                          <span>
                            {grp.pod.name} ({grp.pod.id})
                          </span>
                          <span className="text-neutral-400">&middot;</span>
                          <span className="text-neutral-600 font-semibold">
                            Lead: {empMap.get(grp.pod.lead_employee_id)?.name || grp.pod.lead_employee_id}
                          </span>
                        </div>
                      </td>
                    </tr>
                  )}
                  {grp.emps.map((emp) => (
                    <tr key={emp.id} className="bg-white even:bg-neutral-50/50 hover:bg-blue-50/30 transition-colors">
                      <td className="sticky left-0 z-20 bg-white border-r-2 border-neutral-200 px-3 py-2">
                        <div className="flex items-center justify-between gap-2">
                          <div className="min-w-0">
                            <div className="font-semibold text-neutral-900 truncate">{emp.name}</div>
                            <div className="text-[10px] text-neutral-500 font-mono flex items-center gap-1.5">
                              <span>{emp.id}</span>
                              {emp.role === "POD_LEAD" && (
                                <span className="px-1.5 py-0.2 rounded-full bg-neutral-100 text-neutral-800 border border-neutral-200 font-sans font-semibold">
                                  LEAD
                                </span>
                              )}
                              {emp.is_floater && (
                                <span className="px-1.5 py-0.2 rounded-full bg-teal-50 text-teal-700 border border-teal-200 font-sans font-semibold">
                                  FLOATER
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </td>

                      {dates.map((d) => {
                        const entry = entryMap.get(`${emp.id}|${d}`);
                        const status = entry?.status || "WEEKLY_OFF";
                        const meta = STATUS_META[status];
                        const wd = WEEKDAY_LABELS[getPythonWeekday(d)];
                        const isWeekend = wd === "Sat" || wd === "Sun";
                        const isPh = holidayMap.has(d);
                        return (
                          <td
                            key={`${emp.id}-${d}`}
                            className={`p-0.5 border-r border-neutral-200/70 text-center ${
                              isPh ? "bg-sky-50/40" : isWeekend ? "bg-neutral-100/50" : ""
                            }`}
                          >
                            <button
                              type="button"
                              onClick={() => openCellEditor(emp, d)}
                              title={`${emp.name} (${d}): ${meta.label}${
                                entry?.assigned_brand_id ? ` • ${entry.assigned_brand_id}` : ""
                              }${entry?.is_manual_override ? " • Manual Override" : ""}`}
                              className={`relative w-full h-7 rounded-md border text-[10px] font-bold transition-colors tabular-nums ${meta.badgeClass}`}
                            >
                              {meta.code}
                              {entry?.is_manual_override && (
                                <span
                                  className="absolute top-0.5 right-0.5 w-1.5 h-1.5 rounded-full bg-neutral-900"
                                  aria-label="Manual override"
                                />
                              )}
                            </button>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Legend */}
        <div className="bg-neutral-50 border-t border-neutral-200 px-4 py-2.5 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-600">
          <div className="flex flex-wrap items-center gap-3">
            {(Object.keys(STATUS_META) as EmployeeStatusType[]).map((st) => (
              <span key={st} className="inline-flex items-center gap-1.5">
                <span
                  className={`px-1.5 py-0.5 rounded border text-[10px] font-bold ${STATUS_META[st].badgeClass}`}
                >
                  {STATUS_META[st].code}
                </span>
                <span>{STATUS_META[st].label}</span>
              </span>
            ))}
          </div>
          <span className="text-slate-500">Click any cell to override status &amp; re-validate live</span>
        </div>
      </div>
    );
  };

  // Group rules by brand
  const rulesByBrand = useMemo(() => {
    const m = new Map<string, BrandProcessRule[]>();
    for (const r of rules) {
      const list = m.get(r.brand_id) || [];
      list.push(r);
      m.set(r.brand_id, list);
    }
    return m;
  }, [rules]);

  // Pod-wise data
  const activePod = podMap.get(selectedPodId) || pods[0];
  const podEmployees = useMemo(
    () => employees.filter((e) => e.pod_id === activePod?.id),
    [employees, activePod]
  );
  const podBrands = useMemo(
    () => brands.filter((b) => b.pod_id === activePod?.id),
    [brands, activePod]
  );

  // Brand-wise filtered brands
  const visibleBrands = useMemo(
    () => (selectedBrandId === "ALL" ? brands : brands.filter((b) => b.id === selectedBrandId)),
    [brands, selectedBrandId]
  );

  // Process-wise filtered rules
  const processRules = useMemo(
    () =>
      selectedProcessId === "ALL"
        ? rules
        : rules.filter((r) => r.process_id === selectedProcessId),
    [rules, selectedProcessId]
  );
  const brandMap = useMemo(() => new Map(brands.map((b) => [b.id, b])), [brands]);

  // Employee-wise filtered employees
  const filteredEmployees = useMemo(() => {
    const q = employeeSearch.trim().toLowerCase();
    if (!q) return employees;
    return employees.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        e.id.toLowerCase().includes(q) ||
        e.pod_id.toLowerCase().includes(q)
    );
  }, [employees, employeeSearch]);

  return (
    <div className="space-y-4">
      {/* 5 Stakeholder View Sub-Tabs + Status Legend */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 bg-white border border-neutral-200 rounded-2xl p-2">
        <div className="flex flex-wrap items-center gap-1">
          {(
            [
              { id: "company", label: "Company-wide Matrix", icon: Building2 },
              { id: "pod", label: "Pod-wise View", icon: Layers },
              { id: "brand", label: "Brand-wise View", icon: Tag },
              { id: "process", label: "Process-wise View", icon: GitBranch },
              { id: "employee", label: "Employee-wise View", icon: User },
            ] as const
          ).map((tab) => {
            const Icon = tab.icon;
            const active = activeView === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveView(tab.id)}
                className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-full text-xs font-semibold transition-colors ${
                  active
                    ? "bg-blue-600 text-white shadow-sm shadow-blue-600/15"
                    : "text-neutral-600 hover:bg-neutral-100 hover:text-neutral-950"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Always-Visible Compact Status Legend */}
        <div className="flex flex-wrap items-center gap-2 px-2 py-1 text-[11px] text-neutral-600 border-t lg:border-t-0 lg:border-l border-neutral-100 pt-2 lg:pt-1 lg:pl-3">
          {(Object.entries(STATUS_META) as [EmployeeStatusType, (typeof STATUS_META)[EmployeeStatusType]][]).map(
            ([key, meta]) => (
              <span key={key} className="inline-flex items-center gap-1">
                <span className={`px-1.5 py-0.5 rounded border text-[10px] font-bold ${meta.badgeClass}`}>
                  {meta.code}
                </span>
                <span className="hidden xl:inline text-neutral-500">{meta.label}</span>
              </span>
            )
          )}
        </div>
      </div>

      {/* 1. COMPANY-WIDE MATRIX */}
      {activeView === "company" && renderEmployeeMatrix(employees, true)}

      {/* 2. POD-WISE VIEW */}
      {activeView === "pod" && (
        <div className="space-y-4">
          <div className="bg-white border border-neutral-200 rounded-xl p-4 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              {pods.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setSelectedPodId(p.id)}
                  className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-colors ${
                    activePod?.id === p.id
                      ? "bg-neutral-900 text-white"
                      : "bg-neutral-100 text-neutral-700 hover:bg-neutral-200"
                  }`}
                >
                  {p.name}
                </button>
              ))}
            </div>
            {activePod && (
              <div className="text-xs text-slate-600 flex flex-wrap items-center gap-3">
                <span>
                  <strong className="text-slate-900">Pod Lead:</strong>{" "}
                  {empMap.get(activePod.lead_employee_id)?.name || activePod.lead_employee_id} (
                  {activePod.lead_employee_id})
                </span>
                <span>
                  <strong className="text-slate-900">Team:</strong> {podEmployees.length} employees
                </span>
                <span>
                  <strong className="text-slate-900">Accounts:</strong> {podBrands.length} brands
                </span>
              </div>
            )}
          </div>

          {renderEmployeeMatrix(podEmployees, false)}

          {/* Pod Brand Coverage Table */}
          <div className="bg-white border border-neutral-200 rounded-xl shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-neutral-200 bg-neutral-50">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                {activePod?.name} — Brand &amp; Process Daily Coverage
              </h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-xs">
                <thead className="bg-neutral-50 border-b border-neutral-200">
                  <tr>
                    <th className="sticky left-0 z-20 bg-neutral-50 border-r border-neutral-200 px-3 py-2 text-left font-semibold text-slate-700 min-w-[200px]">
                      Brand / Process
                    </th>
                    {dates.map((d) => (
                      <th key={d} className="px-1 py-2 text-center font-semibold text-slate-600 min-w-[44px] tabular-nums">
                        {d.slice(8, 10)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {podBrands.flatMap((brand) =>
                    (rulesByBrand.get(brand.id) || []).map((rule) => (
                      <tr key={rule.id} className="hover:bg-neutral-50/60">
                        <td className="sticky left-0 z-10 bg-white border-r border-neutral-200 px-3 py-2 font-medium text-slate-900">
                          <div>{brand.name}</div>
                          <div className="text-[10px] text-slate-500">
                            {procMap.get(rule.process_id)?.code || rule.process_id} &middot;{" "}
                            {rule.calendar_type}
                          </div>
                        </td>
                        {dates.map((d) => (
                          <td key={`${rule.id}-${d}`} className="p-1 text-center border-r border-neutral-100">
                            {renderCoverageBadge(coverageMap.get(`${brand.id}|${rule.process_id}|${d}`))}
                          </td>
                        ))}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* 3. BRAND-WISE VIEW */}
      {activeView === "brand" && (
        <div className="space-y-4">
          <div className="bg-white border border-neutral-200 rounded-xl p-4 shadow-sm flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <label className="text-xs font-semibold text-slate-700">Filter Brand:</label>
              <select
                value={selectedBrandId}
                onChange={(e) => setSelectedBrandId(e.target.value)}
                className="text-xs border border-neutral-200 rounded-lg px-3 py-1.5 bg-neutral-50 text-slate-900 font-medium focus:outline-none focus:ring-2 focus:ring-neutral-900/20"
              >
                <option value="ALL">All Brands ({brands.length})</option>
                {brands.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name} ({b.id})
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-[11px]">
              <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 font-semibold">
                1/1 COVERED
              </span>
              <span className="px-2 py-0.5 rounded bg-teal-50 text-teal-800 border border-teal-200 font-semibold">
                1/1 BK BACKUP
              </span>
              <span className="px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-300 font-semibold">
                1/2 SHORT
              </span>
              <span className="px-2 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-300 font-semibold">
                0/1 GAP
              </span>
              <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-400 font-medium">
                — NOT OPERATING
              </span>
            </div>
          </div>

          <div className="space-y-3">
            {visibleBrands.map((brand) => {
              const bRules = rulesByBrand.get(brand.id) || [];
              const bAllocs = allocations.filter((a) => a.brand_id === brand.id);
              const primaryNames = Array.from(
                new Set(
                  bAllocs
                    .filter((a) => a.allocation_type === "PRIMARY")
                    .map((a) => empMap.get(a.employee_id)?.name || a.employee_id)
                )
              );
              const backupNames = Array.from(
                new Set(
                  bAllocs
                    .filter((a) => a.allocation_type === "BACKUP")
                    .map((a) => empMap.get(a.employee_id)?.name || a.employee_id)
                )
              );
              return (
                <div
                  key={brand.id}
                  className="bg-white border border-neutral-200 rounded-xl shadow-sm overflow-hidden"
                >
                  <div className="px-4 py-3 bg-neutral-50 border-b border-neutral-200 flex flex-col md:flex-row md:items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-bold text-slate-900">{brand.name}</span>
                      <span className="text-xs font-mono text-slate-500">({brand.id})</span>
                      <span className="text-[11px] font-semibold px-2 py-0.5 rounded bg-neutral-100 text-neutral-800">
                        {brand.staffing_model.replace(/_/g, " ")}
                      </span>
                      <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-slate-200 text-slate-700">
                        {podMap.get(brand.pod_id)?.name || brand.pod_id}
                      </span>
                    </div>
                    <div className="text-xs text-slate-600 flex flex-wrap items-center gap-3">
                      <span>
                        <strong className="text-slate-800">Primary:</strong>{" "}
                        {primaryNames.length > 0 ? primaryNames.join(", ") : "None"}
                      </span>
                      <span>
                        <strong className="text-slate-800">Backup:</strong>{" "}
                        {backupNames.length > 0 ? backupNames.join(", ") : "None"}
                      </span>
                    </div>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-xs">
                      <thead className="bg-white border-b border-neutral-200">
                        <tr>
                          <th className="sticky left-0 z-20 bg-white border-r border-neutral-200 px-3 py-2 text-left font-semibold text-slate-700 min-w-[220px]">
                            Process &amp; Operating Calendar
                          </th>
                          {dates.map((d) => (
                            <th
                              key={d}
                              className="px-1 py-2 text-center font-semibold text-slate-500 min-w-[46px] tabular-nums"
                            >
                              {d.slice(8, 10)}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {bRules.map((rule) => {
                          const proc = procMap.get(rule.process_id);
                          return (
                            <tr key={rule.id} className="hover:bg-neutral-50/50">
                              <td className="sticky left-0 z-10 bg-white border-r border-neutral-200 px-3 py-2">
                                <div className="flex items-center gap-1.5">
                                  <span className="font-semibold text-slate-900">
                                    {proc ? `${proc.code} — ${proc.name}` : rule.process_id}
                                  </span>
                                </div>
                                <div className="flex flex-wrap items-center gap-1.5 mt-0.5">
                                  <span className="text-[10px] font-semibold px-1.5 py-0.2 rounded bg-slate-100 text-slate-700">
                                    {rule.calendar_type}
                                  </span>
                                  <span className="text-[10px] text-slate-500 tabular-nums">
                                    min: {rule.min_staffing}
                                  </span>
                                </div>
                              </td>
                              {dates.map((d) => (
                                <td
                                  key={`${rule.id}-${d}`}
                                  className="p-1 text-center border-r border-neutral-100"
                                >
                                  {renderCoverageBadge(
                                    coverageMap.get(`${brand.id}|${rule.process_id}|${d}`)
                                  )}
                                </td>
                              ))}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 4. PROCESS-WISE VIEW */}
      {activeView === "process" && (
        <div className="space-y-4">
          <div className="bg-white border border-neutral-200 rounded-xl p-4 shadow-sm flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setSelectedProcessId("ALL")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                selectedProcessId === "ALL"
                  ? "bg-neutral-900 text-white"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
            >
              All Processes
            </button>
            {processes.map((proc) => (
              <button
                key={proc.id}
                type="button"
                onClick={() => setSelectedProcessId(proc.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                  selectedProcessId === proc.id
                    ? "bg-neutral-900 text-white"
                    : "bg-neutral-100 text-neutral-700 hover:bg-neutral-200"
                }`}
              >
                {proc.code} — {proc.name}
              </button>
            ))}
          </div>

          <div className="bg-white border border-neutral-200 rounded-xl shadow-sm overflow-hidden">
            <div className="overflow-x-auto max-h-[600px]">
              <table className="w-full border-collapse text-xs">
                <thead className="sticky top-0 z-30 bg-neutral-50 border-b border-neutral-200">
                  <tr>
                    <th className="sticky left-0 z-40 bg-neutral-50 border-r border-neutral-200 px-3 py-2.5 text-left font-semibold text-slate-700 min-w-[220px]">
                      Brand &middot; Process
                    </th>
                    {dates.map((d) => (
                      <th
                        key={d}
                        className="px-1 py-2.5 text-center font-semibold text-slate-600 min-w-[46px] tabular-nums"
                      >
                        {d.slice(8, 10)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {processRules.map((rule) => {
                    const brand = brandMap.get(rule.brand_id);
                    const proc = procMap.get(rule.process_id);
                    return (
                      <tr key={rule.id} className="hover:bg-neutral-50/50">
                        <td className="sticky left-0 z-20 bg-white border-r border-neutral-200 px-3 py-2">
                          <div className="font-semibold text-slate-900">
                            {brand?.name || rule.brand_id}
                          </div>
                          <div className="text-[10px] text-slate-500">
                            {proc?.code || rule.process_id} &middot; {rule.calendar_type}
                          </div>
                        </td>
                        {dates.map((d) => (
                          <td
                            key={`${rule.id}-${d}`}
                            className="p-1 text-center border-r border-neutral-100"
                          >
                            {renderCoverageBadge(
                              coverageMap.get(`${rule.brand_id}|${rule.process_id}|${d}`)
                            )}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* 5. EMPLOYEE-WISE VIEW & WEEKLY-OFF FAIRNESS SUMMARY */}
      {activeView === "employee" && (
        <div className="space-y-4">
          <div className="bg-white border border-neutral-200 rounded-xl p-4 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="relative flex-1 max-w-sm">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={employeeSearch}
                onChange={(e) => setEmployeeSearch(e.target.value)}
                placeholder="Search employee by name, ID, or pod..."
                className="w-full pl-9 pr-3 py-1.5 text-xs bg-neutral-50 border border-neutral-200 rounded-lg text-slate-900 focus:outline-none focus:ring-2 focus:ring-neutral-900/20"
              />
            </div>
            <div className="text-xs text-slate-500">
              Showing {filteredEmployees.length} of {employees.length} employees &middot; Weekly-Off Fairness Summary
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {filteredEmployees.map((emp) => {
              const empEntries = dates.map((d) => ({
                date: d,
                entry: entryMap.get(`${emp.id}|${d}`),
              }));
              const counts = {
                W: empEntries.filter((x) => x.entry?.status === "WORKING").length,
                WO: empEntries.filter((x) => x.entry?.status === "WEEKLY_OFF").length,
                PH: empEntries.filter((x) => x.entry?.status === "PUBLIC_HOLIDAY").length,
                LV: empEntries.filter((x) => x.entry?.status === "PLANNED_LEAVE").length,
                CO: empEntries.filter((x) => x.entry?.status === "COMP_OFF").length,
                BK: empEntries.filter((x) => x.entry?.status === "BACKUP_COVERAGE").length,
              };
              const empAllocs = allocations.filter((a) => a.employee_id === emp.id);
              const assignedLabels = Array.from(
                new Set(
                  empAllocs.map(
                    (a) =>
                      `${brandMap.get(a.brand_id)?.name || a.brand_id} (${
                        procMap.get(a.process_id)?.code || a.process_id
                      })`
                  )
                )
              );

              return (
                <div
                  key={emp.id}
                  className="bg-white border border-neutral-200 rounded-xl p-4 shadow-sm space-y-3"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <h4 className="text-sm font-bold text-slate-900">{emp.name}</h4>
                        <span className="text-xs font-mono text-slate-500">{emp.id}</span>
                        {emp.role === "POD_LEAD" && (
                          <span className="px-1.5 py-0.5 rounded bg-neutral-100 text-neutral-800 text-[10px] font-semibold">
                            POD LEAD
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        {podMap.get(emp.pod_id)?.name || emp.pod_id} &middot; Shift: {emp.shift} &middot;
                        Pref Off: {WEEKDAY_LABELS[emp.preferred_weekly_off] ?? "Sun"} ({emp.weekly_off_rule})
                      </div>
                    </div>
                  </div>

                  {/* Assigned Brands */}
                  <div className="text-xs text-slate-600">
                    <span className="font-semibold text-slate-800">Assigned: </span>
                    {assignedLabels.length > 0 ? assignedLabels.join(", ") : "Floater / Unassigned"}
                  </div>

                  {/* Fairness Summary Pills */}
                  <div className="grid grid-cols-6 gap-1.5 text-center text-[11px] tabular-nums">
                    <div className="bg-emerald-50 border border-emerald-200 rounded-lg py-1">
                      <div className="font-bold text-emerald-800">{counts.W}</div>
                      <div className="text-[10px] text-emerald-700">Work</div>
                    </div>
                    <div className="bg-slate-100 border border-neutral-200 rounded-lg py-1">
                      <div className="font-bold text-slate-800">{counts.WO}</div>
                      <div className="text-[10px] text-slate-600">Off</div>
                    </div>
                    <div className="bg-sky-50 border border-sky-200 rounded-lg py-1">
                      <div className="font-bold text-sky-800">{counts.PH}</div>
                      <div className="text-[10px] text-sky-700">PH</div>
                    </div>
                    <div className="bg-amber-50 border border-amber-200 rounded-lg py-1">
                      <div className="font-bold text-amber-800">{counts.LV}</div>
                      <div className="text-[10px] text-amber-700">Leave</div>
                    </div>
                    <div className="bg-purple-50 border border-purple-200 rounded-lg py-1">
                      <div className="font-bold text-purple-800">{counts.CO}</div>
                      <div className="text-[10px] text-purple-700">Comp</div>
                    </div>
                    <div className="bg-teal-50 border border-teal-200 rounded-lg py-1">
                      <div className="font-bold text-teal-800">{counts.BK}</div>
                      <div className="text-[10px] text-teal-700">Backup</div>
                    </div>
                  </div>

                  {/* Compact Clickable Day Strip */}
                  <div className="grid grid-cols-11 gap-1 pt-1">
                    {empEntries.map(({ date, entry }) => {
                      const st = entry?.status || "WEEKLY_OFF";
                      const meta = STATUS_META[st];
                      return (
                        <button
                          key={date}
                          type="button"
                          onClick={() => openCellEditor(emp, date)}
                          title={`${date}: ${meta.label}`}
                          className={`relative py-1 rounded border text-[10px] font-semibold tabular-nums ${meta.badgeClass}`}
                        >
                          <div className="text-[9px] opacity-70">{date.slice(8, 10)}</div>
                          <div>{meta.code}</div>
                          {entry?.is_manual_override && (
                            <span className="absolute top-0.5 right-0.5 w-1 h-1 rounded-full bg-neutral-900" />
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Interactive Cell Override Modal */}
      {editingCell && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-[1px]">
          <div className="bg-white border border-neutral-200 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
            <div className="px-5 py-4 border-b border-neutral-200 flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-slate-900">Override Roster Cell</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {editingCell.employee.name} ({editingCell.employee.id}) &middot;{" "}
                  <span className="font-mono font-semibold text-slate-700">{editingCell.date}</span>
                </p>
              </div>
              <button
                type="button"
                onClick={() => setEditingCell(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveOverride} className="p-5 space-y-4">
              {overrideError && (
                <div className="flex items-center gap-2 bg-rose-50 border border-rose-200 text-rose-800 px-3 py-2 rounded-lg text-xs">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />
                  <span>{overrideError}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Employee Status
                </label>
                <select
                  value={overrideStatus}
                  onChange={(e) => setOverrideStatus(e.target.value as EmployeeStatusType)}
                  className="w-full px-3 py-2 text-sm bg-neutral-50 border border-neutral-200 rounded-lg text-slate-900 focus:outline-none focus:ring-2 focus:ring-neutral-900/20"
                >
                  {(Object.keys(STATUS_META) as EmployeeStatusType[]).map((st) => (
                    <option key={st} value={st}>
                      {STATUS_META[st].code} — {STATUS_META[st].label}
                    </option>
                  ))}
                </select>
              </div>

              {(overrideStatus === "WORKING" || overrideStatus === "BACKUP_COVERAGE") && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                      Assigned Brand (optional)
                    </label>
                    <select
                      value={overrideBrandId}
                      onChange={(e) => setOverrideBrandId(e.target.value)}
                      className="w-full px-2.5 py-2 text-xs bg-neutral-50 border border-neutral-200 rounded-lg text-slate-900"
                    >
                      <option value="">Default / Primary</option>
                      {brands.map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.name} ({b.id})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                      Process (optional)
                    </label>
                    <select
                      value={overrideProcessId}
                      onChange={(e) => setOverrideProcessId(e.target.value)}
                      className="w-full px-2.5 py-2 text-xs bg-neutral-50 border border-neutral-200 rounded-lg text-slate-900"
                    >
                      <option value="">Default / All</option>
                      {processes.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.code} — {p.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Override Note (optional)
                </label>
                <input
                  type="text"
                  value={overrideNotes}
                  onChange={(e) => setOverrideNotes(e.target.value)}
                  placeholder="e.g., Swap shift or emergency backup"
                  className="w-full px-3 py-2 text-xs bg-neutral-50 border border-neutral-200 rounded-lg text-slate-900 focus:outline-none focus:ring-2 focus:ring-neutral-900/20"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setEditingCell(null)}
                  className="px-4 py-2 rounded-lg border border-neutral-200 text-xs font-semibold text-slate-700 hover:bg-neutral-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingOverride}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-neutral-900 hover:bg-neutral-800 text-white text-xs font-semibold shadow-sm disabled:opacity-50"
                >
                  {savingOverride && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Save &amp; Re-Validate
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
