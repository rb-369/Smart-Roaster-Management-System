"use client";

import React, { useState } from "react";
import {
  Users,
  Tag,
  Link2,
  CalendarOff,
  Plus,
  Trash2,
  Pencil,
  CheckCircle2,
  XCircle,
  X,
  Loader2,
  Eye,
  ShieldAlert,
} from "lucide-react";
import {
  Allocation,
  Brand,
  BrandProcessRule,
  Employee,
  LeaveAndCompOff,
  LeaveImpactPreviewResponse,
  MonthlyRosterResponse,
  Pod,
  Process,
  PublicHoliday,
  WEEKDAY_LABELS,
  POD_COLOR_OPTIONS,
  getPodColorTheme,
  approveLeave,
  createAllocation,
  createBrand,
  createEmployee,
  createHoliday,
  createLeave,
  createPod,
  createRule,
  deleteAllocation,
  deleteBrand,
  deleteEmployee,
  deleteHoliday,
  deleteLeave,
  deletePod,
  deleteRule,
  fetchMonthlyRoster,
  previewAdhocLeaveImpact,
  rejectLeave,
  updateBrand,
  updateEmployee,
  updatePod,
  updateRule,
} from "@/lib/api";

export type ManagementSubTab = "team" | "brands" | "allocations" | "leaves";

interface ManagementTabsProps {
  month: string;
  pods: Pod[];
  processes: Process[];
  employees: Employee[];
  brands: Brand[];
  rules: BrandProcessRule[];
  allocations: Allocation[];
  leaves: LeaveAndCompOff[];
  holidays: PublicHoliday[];
  initialSubTab?: ManagementSubTab;
  onEntitiesChanged: () => Promise<void>;
  onRosterUpdated: (roster: MonthlyRosterResponse) => void;
}

export default function ManagementTabs({
  month,
  pods,
  processes,
  employees,
  brands,
  rules,
  allocations,
  leaves,
  holidays,
  initialSubTab = "team",
  onEntitiesChanged,
  onRosterUpdated,
}: ManagementTabsProps) {
  const [subTab, setSubTab] = useState<ManagementSubTab>(initialSubTab);
  const [busy, setBusy] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  React.useEffect(() => {
    setSubTab(initialSubTab);
  }, [initialSubTab]);

  const empMap = new Map(employees.map((e) => [e.id, e]));
  const podMap = new Map(pods.map((p) => [p.id, p]));
  const brandMap = new Map(brands.map((b) => [b.id, b]));
  const procMap = new Map(processes.map((p) => [p.id, p]));

  // ── Pod Form State ──
  const [podModal, setPodModal] = useState<{ mode: "add" | "edit"; data: Pod } | null>(null);

  // ── Employee Form State ──
  const [empModal, setEmpModal] = useState<{ mode: "add" | "edit"; data: Employee } | null>(null);

  // ── Brand Form State ──
  const [brandModal, setBrandModal] = useState<{ mode: "add" | "edit"; data: Brand } | null>(null);

  // ── Rule Form State ──
  const [ruleModal, setRuleModal] = useState<{
    mode: "add" | "edit";
    data: BrandProcessRule;
    overridesText: string;
  } | null>(null);

  // ── Allocation Form State ──
  const [newAlloc, setNewAlloc] = useState<Allocation>({
    id: "",
    employee_id: employees[0]?.id || "",
    brand_id: brands[0]?.id || "",
    process_id: processes[0]?.id || "",
    allocation_type: "PRIMARY",
  });

  // ── Leave Form State ──
  const [newLeave, setNewLeave] = useState<LeaveAndCompOff>({
    id: "",
    employee_id: employees[0]?.id || "",
    start_date: `${month}-15`,
    end_date: `${month}-15`,
    type: "PLANNED_LEAVE",
    status: "APPROVED",
    reason: "",
  });
  const [leavePreview, setLeavePreview] = useState<LeaveImpactPreviewResponse | null>(null);
  const [leavePreviewBusy, setLeavePreviewBusy] = useState(false);
  const [leavePreviewError, setLeavePreviewError] = useState<string | null>(null);

  const effectiveLeaveEmployeeId = newLeave.employee_id || employees[0]?.id || "";
  const canPreviewAdhocLeave = Boolean(
    effectiveLeaveEmployeeId && newLeave.start_date && newLeave.end_date
  );

  const handlePreviewAdhocLeave = async () => {
    if (!canPreviewAdhocLeave) return;
    try {
      setLeavePreviewBusy(true);
      setLeavePreviewError(null);
      const res = await previewAdhocLeaveImpact(
        {
          employee_id: effectiveLeaveEmployeeId,
          start_date: newLeave.start_date,
          end_date: newLeave.end_date,
          type: newLeave.type,
        },
        month
      );
      setLeavePreview(res);
    } catch (err: unknown) {
      setLeavePreviewError(
        err instanceof Error ? err.message : "Failed to preview roster impact"
      );
    } finally {
      setLeavePreviewBusy(false);
    }
  };

  // ── Holiday Form State ──
  const [newHoliday, setNewHoliday] = useState<PublicHoliday>({
    id: "",
    date: `${month}-25`,
    name: "",
    is_national: true,
  });

  const runAction = async (fn: () => Promise<unknown>, successText: string, actionKey?: string) => {
    try {
      setBusy(true);
      if (actionKey) setBusyAction(actionKey);
      setErrorMsg(null);
      setStatusMsg(null);
      await fn();
      await onEntitiesChanged();
      setStatusMsg(successText);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Operation failed");
    } finally {
      setBusy(false);
      setBusyAction(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Sub-tab Navigation */}
      <div className="flex flex-wrap items-center gap-1.5 bg-white border border-neutral-200 rounded-xl p-1.5 shadow-sm">
        {(
          [
            { id: "team", label: `Team & Pods (${employees.length})`, icon: Users },
            { id: "brands", label: `Brands & Rules (${brands.length})`, icon: Tag },
            { id: "allocations", label: `Allocations (${allocations.length})`, icon: Link2 },
            { id: "leaves", label: `Leaves & Holidays (${leaves.length})`, icon: CalendarOff },
          ] as const
        ).map((t) => {
          const Icon = t.icon;
          const active = subTab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setSubTab(t.id)}
              className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-full text-xs font-semibold transition-colors ${
                active
                  ? "bg-blue-600 text-white shadow-sm shadow-blue-600/15"
                  : "text-neutral-600 hover:bg-neutral-100 hover:text-neutral-950"
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          );
        })}
      </div>

      {errorMsg && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 px-4 py-2.5 rounded-xl text-xs font-medium">
          {errorMsg}
        </div>
      )}
      {statusMsg && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 px-4 py-2.5 rounded-xl text-xs font-medium flex items-center justify-between">
          <span>{statusMsg}</span>
          <button type="button" onClick={() => setStatusMsg(null)} className="text-emerald-700">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* ─── TAB 1: TEAM & PODS ────────────────────────────────────────────── */}
      {subTab === "team" && (
        <div className="space-y-6">
          {/* Pods Section */}
          <div className="bg-white border border-neutral-200 rounded-xl shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-neutral-200 bg-neutral-50 flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                Operational Pods ({pods.length})
              </h3>
              <button
                type="button"
                onClick={() =>
                  setPodModal({
                    mode: "add",
                    data: {
                      id: `POD-${pods.length + 1}`,
                      name: "",
                      lead_employee_id: employees[0]?.id || "",
                      color: POD_COLOR_OPTIONS[pods.length % 4].key,
                    },
                  })
                }
                className="inline-flex items-center gap-1 px-3.5 py-1.5 rounded-full bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-sm shadow-blue-600/15"
              >
                <Plus className="w-3.5 h-3.5" />
                Add Pod
              </button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 p-4">
              {pods.map((pod, idx) => {
                const theme = getPodColorTheme(pod.color, idx);
                return (
                <div
                  key={pod.id}
                  className={`border border-neutral-200 border-t-2 ${theme.borderTop} rounded-xl p-3.5 bg-white flex items-start justify-between gap-2`}
                >
                  <div>
                    <div className="text-sm font-bold text-neutral-950">{pod.name}</div>
                    <span className={`inline-block mt-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold border ${theme.badge}`}>
                      {pod.id}
                    </span>
                    <div className="text-xs text-neutral-600 mt-1.5">
                      Lead: {empMap.get(pod.lead_employee_id)?.name || pod.lead_employee_id}
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() =>
                        setPodModal({
                          mode: "edit",
                          data: { ...pod, color: pod.color || POD_COLOR_OPTIONS[idx % 4].key },
                        })
                      }
                      className="p-1 text-slate-500 hover:text-neutral-950"
                      title="Edit Pod"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        runAction(() => deletePod(pod.id), `Deleted pod ${pod.id}`, `del-pod-${pod.id}`)
                      }
                      className="p-1 text-slate-400 hover:text-rose-600 disabled:opacity-50"
                      title="Delete Pod"
                    >
                      {busyAction === `del-pod-${pod.id}` ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin text-rose-600" />
                      ) : (
                        <Trash2 className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </div>
                </div>
                );
              })}
            </div>
          </div>

          {/* Employees Section */}
          <div className="bg-white border border-neutral-200 rounded-xl shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-neutral-200 bg-neutral-50 flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                Employees ({employees.length})
              </h3>
              <button
                type="button"
                onClick={() =>
                  setEmpModal({
                    mode: "add",
                    data: {
                      id: `EMP-${String(employees.length + 1).padStart(2, "0")}`,
                      name: "",
                      email: "",
                      role: "ASSOCIATE",
                      pod_id: pods[0]?.id || "POD-1",
                      skills: ["CS"],
                      default_weekly_off: 6,
                      preferred_weekly_off: 6,
                      weekly_off_rule: "FIXED",
                      shift: "DAY_9_18",
                      is_floater: false,
                      active: true,
                    },
                  })
                }
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-neutral-900 hover:bg-neutral-800 text-white text-xs font-semibold"
              >
                <Plus className="w-3.5 h-3.5" />
                Add Employee
              </button>
            </div>
            <div className="overflow-x-auto max-h-[500px]">
              <table className="w-full text-left text-xs">
                <thead className="bg-neutral-50 border-b border-neutral-200 sticky top-0 text-slate-600">
                  <tr>
                    <th className="px-3 py-2.5 font-semibold">Employee</th>
                    <th className="px-3 py-2.5 font-semibold">Pod / Role</th>
                    <th className="px-3 py-2.5 font-semibold">Default Off</th>
                    <th className="px-3 py-2.5 font-semibold">Pref Off</th>
                    <th className="px-3 py-2.5 font-semibold">Rule / Shift</th>
                    <th className="px-3 py-2.5 font-semibold">Skills</th>
                    <th className="px-3 py-2.5 text-right font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {employees.map((emp) => (
                    <tr key={emp.id} className="hover:bg-neutral-50/70">
                      <td className="px-3 py-2.5">
                        <div className="font-semibold text-slate-900">{emp.name}</div>
                        <div className="text-[11px] font-mono text-slate-500">
                          {emp.id} &middot; {emp.email}
                        </div>
                      </td>
                      <td className="px-3 py-2.5">
                        <div className="text-slate-800 font-medium">
                          {podMap.get(emp.pod_id)?.name || emp.pod_id}
                        </div>
                        <div className="text-[11px] text-slate-500">
                          {emp.role}
                          {emp.is_floater ? " • FLOATER" : ""}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 font-medium text-slate-700">
                        {WEEKDAY_LABELS[emp.default_weekly_off] ?? emp.default_weekly_off}
                      </td>
                      <td className="px-3 py-2.5 font-medium text-slate-700">
                        {WEEKDAY_LABELS[emp.preferred_weekly_off] ?? emp.preferred_weekly_off}
                      </td>
                      <td className="px-3 py-2.5 text-slate-600">
                        {emp.weekly_off_rule} &middot; {emp.shift}
                      </td>
                      <td className="px-3 py-2.5">
                        <div className="flex flex-wrap gap-1">
                          {(emp.skills || []).map((s) => (
                            <span
                              key={s}
                              className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 text-[10px] font-semibold"
                            >
                              {s}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <div className="inline-flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => setEmpModal({ mode: "edit", data: { ...emp } })}
                            className="p-1.5 rounded hover:bg-slate-100 text-slate-600 hover:text-neutral-950"
                            title="Edit Employee"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() =>
                              runAction(
                                () => deleteEmployee(emp.id),
                                `Deleted employee ${emp.id}`,
                                `del-emp-${emp.id}`
                              )
                            }
                            className="p-1.5 rounded hover:bg-rose-50 text-slate-400 hover:text-rose-600 disabled:opacity-50"
                            title="Delete Employee"
                          >
                            {busyAction === `del-emp-${emp.id}` ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin text-rose-600" />
                            ) : (
                              <Trash2 className="w-3.5 h-3.5" />
                            )}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ─── TAB 2: BRANDS & OPERATING RULES ───────────────────────────────── */}
      {subTab === "brands" && (
        <div className="space-y-6">
          {/* Brands Table */}
          <div className="bg-white border border-neutral-200 rounded-xl shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-neutral-200 bg-neutral-50 flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                D2C Brands ({brands.length})
              </h3>
              <button
                type="button"
                onClick={() =>
                  setBrandModal({
                    mode: "add",
                    data: {
                      id: `BRD-${String(brands.length + 1).padStart(2, "0")}`,
                      name: "",
                      pod_id: pods[0]?.id || "POD-1",
                      tier: "STANDARD",
                      staffing_model: "SINGLE_RESOURCE",
                    },
                  })
                }
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-neutral-900 hover:bg-neutral-800 text-white text-xs font-semibold"
              >
                <Plus className="w-3.5 h-3.5" />
                Add Brand
              </button>
            </div>
            <div className="overflow-x-auto max-h-[340px]">
              <table className="w-full text-left text-xs">
                <thead className="bg-neutral-50 border-b border-neutral-200 sticky top-0 text-slate-600">
                  <tr>
                    <th className="px-3 py-2.5 font-semibold">Brand</th>
                    <th className="px-3 py-2.5 font-semibold">Pod</th>
                    <th className="px-3 py-2.5 font-semibold">Tier</th>
                    <th className="px-3 py-2.5 font-semibold">Staffing Model</th>
                    <th className="px-3 py-2.5 text-right font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {brands.map((b) => (
                    <tr key={b.id} className="hover:bg-neutral-50/70">
                      <td className="px-3 py-2">
                        <span className="font-semibold text-slate-900">{b.name}</span>{" "}
                        <span className="font-mono text-slate-500 text-[11px]">({b.id})</span>
                      </td>
                      <td className="px-3 py-2 text-slate-700">
                        {podMap.get(b.pod_id)?.name || b.pod_id}
                      </td>
                      <td className="px-3 py-2 text-slate-700">{b.tier}</td>
                      <td className="px-3 py-2">
                        <span className="px-2 py-0.5 rounded bg-neutral-100 text-neutral-800 text-[11px] font-semibold">
                          {b.staffing_model}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          type="button"
                          onClick={() => setBrandModal({ mode: "edit", data: { ...b } })}
                          className="p-1.5 rounded hover:bg-slate-100 text-slate-600 hover:text-neutral-950"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() =>
                            runAction(() => deleteBrand(b.id), `Deleted brand ${b.id}`, `del-brand-${b.id}`)
                          }
                          className="p-1.5 rounded hover:bg-rose-50 text-slate-400 hover:text-rose-600 disabled:opacity-50"
                          title="Delete Brand"
                        >
                          {busyAction === `del-brand-${b.id}` ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin text-rose-600" />
                          ) : (
                            <Trash2 className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Operating Rules Table */}
          <div className="bg-white border border-neutral-200 rounded-xl shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-neutral-200 bg-neutral-50 flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                Brand-Process Operating Rules ({rules.length})
              </h3>
              <button
                type="button"
                onClick={() =>
                  setRuleModal({
                    mode: "add",
                    data: {
                      id: `RULE-${String(rules.length + 1).padStart(2, "0")}`,
                      brand_id: brands[0]?.id || "",
                      process_id: processes[0]?.id || "",
                      calendar_type: "365_DAYS",
                      min_staffing: 1,
                      day_min_staffing_overrides: {},
                    },
                    overridesText: "{}",
                  })
                }
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-neutral-900 hover:bg-neutral-800 text-white text-xs font-semibold"
              >
                <Plus className="w-3.5 h-3.5" />
                Add Operating Rule
              </button>
            </div>
            <div className="overflow-x-auto max-h-[420px]">
              <table className="w-full text-left text-xs">
                <thead className="bg-neutral-50 border-b border-neutral-200 sticky top-0 text-slate-600">
                  <tr>
                    <th className="px-3 py-2.5 font-semibold">Brand</th>
                    <th className="px-3 py-2.5 font-semibold">Process</th>
                    <th className="px-3 py-2.5 font-semibold">Calendar Type</th>
                    <th className="px-3 py-2.5 font-semibold">Min Staffing</th>
                    <th className="px-3 py-2.5 font-semibold">Day Overrides (0=Mon..6=Sun)</th>
                    <th className="px-3 py-2.5 text-right font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rules.map((r) => (
                    <tr key={r.id} className="hover:bg-neutral-50/70">
                      <td className="px-3 py-2 font-medium text-slate-900">
                        {brandMap.get(r.brand_id)?.name || r.brand_id}
                      </td>
                      <td className="px-3 py-2 text-neutral-800 font-semibold">
                        {procMap.get(r.process_id)?.code || r.process_id}
                      </td>
                      <td className="px-3 py-2">
                        <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-800 font-mono text-[11px]">
                          {r.calendar_type}
                        </span>
                      </td>
                      <td className="px-3 py-2 tabular-nums font-semibold">{r.min_staffing}</td>
                      <td className="px-3 py-2 font-mono text-[11px] text-slate-600">
                        {Object.keys(r.day_min_staffing_overrides || {}).length > 0
                          ? Object.entries(r.day_min_staffing_overrides)
                              .map(([k, v]) => `${WEEKDAY_LABELS[Number(k)] ?? k}:${v}`)
                              .join(", ")
                          : "—"}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          type="button"
                          onClick={() =>
                            setRuleModal({
                              mode: "edit",
                              data: { ...r },
                              overridesText: JSON.stringify(r.day_min_staffing_overrides || {}),
                            })
                          }
                          className="p-1.5 rounded hover:bg-slate-100 text-slate-600 hover:text-neutral-950"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() =>
                            runAction(() => deleteRule(r.id), `Deleted rule ${r.id}`, `del-rule-${r.id}`)
                          }
                          className="p-1.5 rounded hover:bg-rose-50 text-slate-400 hover:text-rose-600 disabled:opacity-50"
                          title="Delete Rule"
                        >
                          {busyAction === `del-rule-${r.id}` ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin text-rose-600" />
                          ) : (
                            <Trash2 className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ─── TAB 3: ALLOCATIONS ────────────────────────────────────────────── */}
      {subTab === "allocations" && (
        <div className="space-y-4">
          {/* Quick Add Allocation */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const id = newAlloc.id.trim() || `ALLOC-${Date.now()}`;
              runAction(
                () => createAllocation({ ...newAlloc, id }),
                `Created allocation ${id}`,
                "add-allocation"
              );
            }}
            className="bg-white border border-neutral-200 rounded-xl p-4 shadow-sm grid grid-cols-1 sm:grid-cols-5 gap-3 items-end"
          >
            <div>
              <label className="block text-[11px] font-semibold text-slate-600 mb-1">Employee</label>
              <select
                value={newAlloc.employee_id}
                onChange={(e) => setNewAlloc({ ...newAlloc, employee_id: e.target.value })}
                className="w-full px-2.5 py-1.5 text-xs bg-neutral-50 border border-neutral-200 rounded-lg"
              >
                {employees.map((emp) => (
                  <option key={emp.id} value={emp.id}>
                    {emp.name} ({emp.id})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-slate-600 mb-1">Brand</label>
              <select
                value={newAlloc.brand_id}
                onChange={(e) => setNewAlloc({ ...newAlloc, brand_id: e.target.value })}
                className="w-full px-2.5 py-1.5 text-xs bg-neutral-50 border border-neutral-200 rounded-lg"
              >
                {brands.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name} ({b.id})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-slate-600 mb-1">Process</label>
              <select
                value={newAlloc.process_id}
                onChange={(e) => setNewAlloc({ ...newAlloc, process_id: e.target.value })}
                className="w-full px-2.5 py-1.5 text-xs bg-neutral-50 border border-neutral-200 rounded-lg"
              >
                {processes.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.code} — {p.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-slate-600 mb-1">Type</label>
              <select
                value={newAlloc.allocation_type}
                onChange={(e) => setNewAlloc({ ...newAlloc, allocation_type: e.target.value })}
                className="w-full px-2.5 py-1.5 text-xs bg-neutral-50 border border-neutral-200 rounded-lg"
              >
                <option value="PRIMARY">PRIMARY</option>
                <option value="BACKUP">BACKUP</option>
              </select>
            </div>
            <button
              type="submit"
              disabled={busy}
              className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-neutral-900 hover:bg-neutral-800 disabled:opacity-60 disabled:cursor-not-allowed text-white text-xs font-semibold transition-all min-w-[130px]"
            >
              {busyAction === "add-allocation" ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Plus className="w-3.5 h-3.5" />
              )}
              {busyAction === "add-allocation" ? "Adding..." : "Add Allocation"}
            </button>
          </form>

          <div className="bg-white border border-neutral-200 rounded-xl shadow-sm overflow-hidden">
            <div className="overflow-x-auto max-h-[500px]">
              <table className="w-full text-left text-xs">
                <thead className="bg-neutral-50 border-b border-neutral-200 sticky top-0 text-slate-600">
                  <tr>
                    <th className="px-3 py-2.5 font-semibold">Employee</th>
                    <th className="px-3 py-2.5 font-semibold">Brand</th>
                    <th className="px-3 py-2.5 font-semibold">Process</th>
                    <th className="px-3 py-2.5 font-semibold">Type</th>
                    <th className="px-3 py-2.5 text-right font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {allocations.map((a) => (
                    <tr key={a.id} className="hover:bg-neutral-50/70">
                      <td className="px-3 py-2 font-medium text-slate-900">
                        {empMap.get(a.employee_id)?.name || a.employee_id}{" "}
                        <span className="font-mono text-slate-400 text-[11px]">({a.employee_id})</span>
                      </td>
                      <td className="px-3 py-2 text-slate-700">
                        {brandMap.get(a.brand_id)?.name || a.brand_id}
                      </td>
                      <td className="px-3 py-2 text-neutral-800 font-semibold">
                        {procMap.get(a.process_id)?.code || a.process_id}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                            a.allocation_type === "PRIMARY"
                              ? "bg-emerald-50 text-emerald-700"
                              : "bg-teal-50 text-teal-700"
                          }`}
                        >
                          {a.allocation_type}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() =>
                            runAction(
                              () => deleteAllocation(a.id),
                              `Deleted allocation ${a.id}`,
                              `del-alloc-${a.id}`
                            )
                          }
                          className="p-1.5 rounded hover:bg-rose-50 text-slate-400 hover:text-rose-600 disabled:opacity-50"
                          title="Delete Allocation"
                        >
                          {busyAction === `del-alloc-${a.id}` ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin text-rose-600" />
                          ) : (
                            <Trash2 className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ─── TAB 4: LEAVES & HOLIDAYS ──────────────────────────────────────── */}
      {subTab === "leaves" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Leaves (2 cols) */}
          <div className="lg:col-span-2 space-y-4">
            <div className="bg-white border border-neutral-200 rounded-xl p-4 shadow-sm space-y-3">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const id = newLeave.id.trim() || `LV-${Date.now()}`;
                  runAction(
                    () =>
                      createLeave({
                        ...newLeave,
                        id,
                        employee_id: effectiveLeaveEmployeeId,
                      }),
                    `Added leave ${id}`,
                    "add-leave"
                  ).then(() => {
                    setLeavePreview(null);
                    setLeavePreviewError(null);
                  });
                }}
                className="grid grid-cols-2 sm:grid-cols-6 gap-2.5 items-end"
              >
                <div className="col-span-2">
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">Employee</label>
                  <select
                    value={effectiveLeaveEmployeeId}
                    onChange={(e) => {
                      setNewLeave({ ...newLeave, employee_id: e.target.value });
                      setLeavePreview(null);
                      setLeavePreviewError(null);
                    }}
                    className="w-full px-2.5 py-1.5 text-xs bg-neutral-50 border border-neutral-200 rounded-lg"
                  >
                    {employees.map((emp) => (
                      <option key={emp.id} value={emp.id}>
                        {emp.name} ({emp.id})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">Start</label>
                  <input
                    type="date"
                    value={newLeave.start_date}
                    onChange={(e) => {
                      setNewLeave({ ...newLeave, start_date: e.target.value });
                      setLeavePreview(null);
                      setLeavePreviewError(null);
                    }}
                    className="w-full px-2 py-1.5 text-xs bg-neutral-50 border border-neutral-200 rounded-lg"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">End</label>
                  <input
                    type="date"
                    value={newLeave.end_date}
                    onChange={(e) => {
                      setNewLeave({ ...newLeave, end_date: e.target.value });
                      setLeavePreview(null);
                      setLeavePreviewError(null);
                    }}
                    className="w-full px-2 py-1.5 text-xs bg-neutral-50 border border-neutral-200 rounded-lg"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">Type</label>
                  <select
                    value={newLeave.type}
                    onChange={(e) => {
                      setNewLeave({ ...newLeave, type: e.target.value });
                      setLeavePreview(null);
                      setLeavePreviewError(null);
                    }}
                    className="w-full px-2 py-1.5 text-xs bg-neutral-50 border border-neutral-200 rounded-lg"
                  >
                    <option value="PLANNED_LEAVE">PLANNED_LEAVE</option>
                    <option value="COMP_OFF">COMP_OFF</option>
                  </select>
                </div>
                <div className="col-span-2 sm:col-span-6 flex flex-wrap items-center justify-end gap-2 pt-1">
                  <button
                    type="button"
                    disabled={!canPreviewAdhocLeave || leavePreviewBusy || busy}
                    onClick={handlePreviewAdhocLeave}
                    className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-white hover:bg-neutral-100 disabled:opacity-50 border border-neutral-300 text-neutral-800 text-xs font-semibold transition-colors"
                  >
                    {leavePreviewBusy ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Eye className="w-3.5 h-3.5" />
                    )}
                    {leavePreviewBusy ? "Previewing..." : "Preview Roster Impact"}
                  </button>
                  <button
                    type="submit"
                    disabled={busy}
                    className="inline-flex items-center justify-center gap-1 px-3 py-2 rounded-lg bg-neutral-900 hover:bg-neutral-800 disabled:opacity-60 disabled:cursor-not-allowed text-white text-xs font-semibold min-w-[70px] transition-all"
                  >
                    {busyAction === "add-leave" ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Plus className="w-3.5 h-3.5" />
                    )}
                    {busyAction === "add-leave" ? "Adding..." : "Add"}
                  </button>
                </div>
              </form>

              {leavePreviewError && (
                <div className="bg-rose-50 border border-rose-200 text-rose-800 px-3 py-2 rounded-lg text-xs font-medium flex items-center justify-between">
                  <span>{leavePreviewError}</span>
                  <button
                    type="button"
                    onClick={() => setLeavePreviewError(null)}
                    className="text-rose-600 hover:text-rose-800"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}

              {leavePreview && (
                <div className="bg-neutral-50 border border-amber-200 rounded-xl p-3 space-y-2 text-xs">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="inline-flex items-center gap-1.5 font-bold text-neutral-900">
                        <ShieldAlert
                          className={`w-3.5 h-3.5 ${
                            leavePreview.new_hard_conflicts_count > 0
                              ? "text-rose-600"
                              : "text-emerald-600"
                          }`}
                        />
                        What-If Impact Summary
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${
                          leavePreview.new_hard_conflicts_count > 0
                            ? "bg-rose-50 text-rose-700 border border-rose-200"
                            : "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        }`}
                      >
                        +{leavePreview.new_hard_conflicts_count} hard conflict
                        {leavePreview.new_hard_conflicts_count === 1 ? "" : "s"} (
                        {leavePreview.hard_conflicts_before} → {leavePreview.hard_conflicts_after})
                      </span>
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-white border border-neutral-200 text-neutral-800">
                        Coverage: {leavePreview.coverage_before.toFixed(1)}% →{" "}
                        {leavePreview.coverage_after.toFixed(1)}%
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setLeavePreview(null)}
                      className="p-1 text-neutral-400 hover:text-neutral-700"
                      title="Close preview"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-[11px] text-neutral-600">
                    <div>
                      <span className="font-semibold text-neutral-800">Affected Brands: </span>
                      {leavePreview.affected_brands.length > 0
                        ? leavePreview.affected_brands.map((b) => b.brand_name).join(", ")
                        : "None"}
                    </div>
                    <div>
                      <span className="font-semibold text-neutral-800">Affected Processes: </span>
                      {leavePreview.affected_processes.length > 0
                        ? leavePreview.affected_processes.join(", ")
                        : "None"}
                    </div>
                    <div>
                      <span className="font-semibold text-neutral-800">Affected Dates: </span>
                      {leavePreview.affected_dates.length > 0
                        ? leavePreview.affected_dates.join(", ")
                        : "None"}
                    </div>
                  </div>

                  {leavePreview.new_conflicts.length > 0 ? (
                    <div className="space-y-1.5 pt-1 border-t border-neutral-200/70">
                      <div className="text-[11px] font-semibold text-neutral-700">
                        New Coverage Gaps &amp; Top Backup Candidates ({leavePreview.new_conflicts.length})
                      </div>
                      <div className="space-y-1.5">
                        {leavePreview.new_conflicts.map((c, idx) => {
                          const topBackup = c.suggested_resolutions?.[0];
                          return (
                            <div
                              key={`${c.date}-${c.brand_id ?? ""}-${c.process_id ?? ""}-${idx}`}
                              className="bg-white border border-neutral-200 rounded-lg px-2.5 py-2 flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 text-[11px]"
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
                    <div className="text-[11px] text-emerald-700 font-medium pt-1 border-t border-neutral-200/70">
                      No new coverage gaps detected for this leave window.
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="bg-white border border-neutral-200 rounded-xl shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b border-neutral-200 bg-neutral-50">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Leaves &amp; Comp-Offs ({leaves.length})
                </h3>
              </div>
              <div className="overflow-x-auto max-h-[420px]">
                <table className="w-full text-left text-xs">
                  <thead className="bg-neutral-50 border-b border-neutral-200 sticky top-0 text-slate-600">
                    <tr>
                      <th className="px-3 py-2 font-semibold">ID / Employee</th>
                      <th className="px-3 py-2 font-semibold">Dates</th>
                      <th className="px-3 py-2 font-semibold">Type</th>
                      <th className="px-3 py-2 font-semibold">Status</th>
                      <th className="px-3 py-2 text-right font-semibold">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {leaves.map((lv) => (
                      <tr key={lv.id} className="hover:bg-neutral-50/70">
                        <td className="px-3 py-2">
                          <div className="font-semibold text-slate-900">
                            {empMap.get(lv.employee_id)?.name || lv.employee_id}
                          </div>
                          <div className="text-[11px] font-mono text-slate-500">
                            {lv.id} &middot; {lv.employee_id}
                          </div>
                        </td>
                        <td className="px-3 py-2 tabular-nums text-slate-700">
                          {lv.start_date} → {lv.end_date}
                        </td>
                        <td className="px-3 py-2 text-slate-700">{lv.type}</td>
                        <td className="px-3 py-2">
                          <span
                            className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                              lv.status === "APPROVED"
                                ? "bg-emerald-50 text-emerald-700"
                                : lv.status === "PENDING"
                                ? "bg-amber-100 text-amber-800"
                                : "bg-slate-100 text-slate-600"
                            }`}
                          >
                            {lv.status}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right">
                          <div className="inline-flex items-center gap-1">
                            {lv.status === "PENDING" && (
                              <>
                                <button
                                  type="button"
                                  disabled={busy}
                                  onClick={() =>
                                    runAction(
                                      async () => {
                                        const res = await approveLeave(lv.id, month);
                                        if (res.roster) {
                                          onRosterUpdated(res.roster);
                                        } else {
                                          onRosterUpdated(await fetchMonthlyRoster(month));
                                        }
                                      },
                                      `Approved ${lv.id} and re-validated roster`,
                                      `approve-leave-${lv.id}`
                                    )
                                  }
                                  className="p-1.5 rounded hover:bg-emerald-50 text-emerald-600 disabled:opacity-50"
                                  title="Approve & Re-validate"
                                >
                                  {busyAction === `approve-leave-${lv.id}` ? (
                                    <Loader2 className="w-4 h-4 animate-spin text-emerald-600" />
                                  ) : (
                                    <CheckCircle2 className="w-4 h-4" />
                                  )}
                                </button>
                                <button
                                  type="button"
                                  disabled={busy}
                                  onClick={() =>
                                    runAction(
                                      () => rejectLeave(lv.id),
                                      `Rejected ${lv.id}`,
                                      `reject-leave-${lv.id}`
                                    )
                                  }
                                  className="p-1.5 rounded hover:bg-slate-100 text-slate-500 disabled:opacity-50"
                                  title="Reject"
                                >
                                  {busyAction === `reject-leave-${lv.id}` ? (
                                    <Loader2 className="w-4 h-4 animate-spin text-slate-500" />
                                  ) : (
                                    <XCircle className="w-4 h-4" />
                                  )}
                                </button>
                              </>
                            )}
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() =>
                                runAction(
                                  () => deleteLeave(lv.id),
                                  `Deleted ${lv.id}`,
                                  `del-leave-${lv.id}`
                                )
                              }
                              className="p-1.5 rounded hover:bg-rose-50 text-slate-400 hover:text-rose-600 disabled:opacity-50"
                              title="Delete"
                            >
                              {busyAction === `del-leave-${lv.id}` ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin text-rose-600" />
                              ) : (
                                <Trash2 className="w-3.5 h-3.5" />
                              )}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Public Holidays (1 col) */}
          <div className="space-y-4">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const id = newHoliday.id.trim() || `PH-${Date.now()}`;
                runAction(
                  () => createHoliday({ ...newHoliday, id }),
                  `Added holiday ${newHoliday.name}`,
                  "add-holiday"
                );
              }}
              className="bg-white border border-neutral-200 rounded-xl p-4 shadow-sm space-y-2.5"
            >
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                Add Public Holiday
              </h4>
              <input
                type="date"
                required
                value={newHoliday.date}
                onChange={(e) => setNewHoliday({ ...newHoliday, date: e.target.value })}
                className="w-full px-2.5 py-1.5 text-xs bg-neutral-50 border border-neutral-200 rounded-lg"
              />
              <input
                type="text"
                required
                placeholder="Holiday name (e.g., Christmas Day)"
                value={newHoliday.name}
                onChange={(e) => setNewHoliday({ ...newHoliday, name: e.target.value })}
                className="w-full px-2.5 py-1.5 text-xs bg-neutral-50 border border-neutral-200 rounded-lg"
              />
              <button
                type="submit"
                disabled={busy}
                className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-neutral-900 hover:bg-neutral-800 disabled:opacity-60 disabled:cursor-not-allowed text-white text-xs font-semibold transition-all"
              >
                {busyAction === "add-holiday" ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Plus className="w-3.5 h-3.5" />
                )}
                {busyAction === "add-holiday" ? "Adding Holiday..." : "Add Holiday"}
              </button>
            </form>

            <div className="bg-white border border-neutral-200 rounded-xl shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b border-neutral-200 bg-neutral-50">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Public Holidays ({holidays.length})
                </h3>
              </div>
              <div className="divide-y divide-slate-100">
                {holidays.map((h) => (
                  <div key={h.id} className="px-4 py-2.5 flex items-center justify-between text-xs">
                    <div>
                      <div className="font-semibold text-slate-900">{h.name}</div>
                      <div className="text-[11px] font-mono text-slate-500">{h.date}</div>
                    </div>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        runAction(
                          () => deleteHoliday(h.id),
                          `Deleted holiday ${h.name}`,
                          `del-holiday-${h.id}`
                        )
                      }
                      className="p-1.5 rounded hover:bg-rose-50 text-slate-400 hover:text-rose-600 disabled:opacity-50"
                      title="Delete Holiday"
                    >
                      {busyAction === `del-holiday-${h.id}` ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin text-rose-600" />
                      ) : (
                        <Trash2 className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ─── MODALS ────────────────────────────────────────────────────────── */}

      {/* Pod Modal */}
      {podModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              runAction(
                () =>
                  podModal.mode === "add"
                    ? createPod(podModal.data).then(() => undefined)
                    : updatePod(podModal.data.id, podModal.data).then(() => undefined),
                `${podModal.mode === "add" ? "Created" : "Updated"} pod ${podModal.data.id}`
              ).then(() => setPodModal(null));
            }}
            className="bg-white border border-neutral-200 rounded-2xl shadow-xl w-full max-w-md p-5 space-y-4"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate-900">
                {podModal.mode === "add" ? "Add Pod" : `Edit Pod ${podModal.data.id}`}
              </h3>
              <button type="button" onClick={() => setPodModal(null)}>
                <X className="w-4 h-4 text-slate-400" />
              </button>
            </div>
            <div className="space-y-3 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Pod ID</label>
                <input
                  type="text"
                  required
                  disabled={podModal.mode === "edit"}
                  value={podModal.data.id}
                  onChange={(e) =>
                    setPodModal({ ...podModal, data: { ...podModal.data, id: e.target.value } })
                  }
                  className="w-full px-3 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                />
              </div>
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Pod Name</label>
                <input
                  type="text"
                  required
                  value={podModal.data.name}
                  onChange={(e) =>
                    setPodModal({ ...podModal, data: { ...podModal.data, name: e.target.value } })
                  }
                  className="w-full px-3 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                />
              </div>
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Pod Lead</label>
                <select
                  value={podModal.data.lead_employee_id}
                  onChange={(e) =>
                    setPodModal({
                      ...podModal,
                      data: { ...podModal.data, lead_employee_id: e.target.value },
                    })
                  }
                  className="w-full px-3 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                >
                  {employees.map((emp) => (
                    <option key={emp.id} value={emp.id}>
                      {emp.name} ({emp.id})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block font-semibold text-slate-700 mb-1.5">Pod Color</label>
                <div className="flex flex-wrap items-center gap-2">
                  {POD_COLOR_OPTIONS.map((c) => {
                    const selected = (podModal.data.color || "") === c.key;
                    return (
                      <button
                        key={c.key}
                        type="button"
                        title={c.label}
                        onClick={() =>
                          setPodModal({
                            ...podModal,
                            data: { ...podModal.data, color: c.key },
                          })
                        }
                        className={`w-6 h-6 rounded-full ${c.swatch} transition-transform ${
                          selected
                            ? "ring-2 ring-offset-2 ring-neutral-900 scale-110"
                            : "opacity-80 hover:opacity-100"
                        }`}
                        aria-label={`Select ${c.label} color`}
                      />
                    );
                  })}
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setPodModal(null)}
                className="px-3 py-2 rounded-lg border border-neutral-200 text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={busy}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-neutral-900 text-white text-xs font-semibold disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                {busy ? (podModal.mode === "add" ? "Creating..." : "Saving...") : "Save Pod"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Employee Modal */}
      {empModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              runAction(
                () =>
                  empModal.mode === "add"
                    ? createEmployee(empModal.data).then(() => undefined)
                    : updateEmployee(empModal.data.id, empModal.data).then(() => undefined),
                `${empModal.mode === "add" ? "Created" : "Updated"} employee ${empModal.data.id}`
              ).then(() => setEmpModal(null));
            }}
            className="bg-white border border-neutral-200 rounded-2xl shadow-xl w-full max-w-lg p-5 space-y-4"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate-900">
                {empModal.mode === "add" ? "Add Employee" : `Edit Employee ${empModal.data.id}`}
              </h3>
              <button type="button" onClick={() => setEmpModal(null)}>
                <X className="w-4 h-4 text-slate-400" />
              </button>
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">ID</label>
                <input
                  type="text"
                  required
                  disabled={empModal.mode === "edit"}
                  value={empModal.data.id}
                  onChange={(e) =>
                    setEmpModal({ ...empModal, data: { ...empModal.data, id: e.target.value } })
                  }
                  className="w-full px-3 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                />
              </div>
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Full Name</label>
                <input
                  type="text"
                  required
                  value={empModal.data.name}
                  onChange={(e) =>
                    setEmpModal({ ...empModal, data: { ...empModal.data, name: e.target.value } })
                  }
                  className="w-full px-3 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                />
              </div>
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Email</label>
                <input
                  type="email"
                  required
                  value={empModal.data.email}
                  onChange={(e) =>
                    setEmpModal({ ...empModal, data: { ...empModal.data, email: e.target.value } })
                  }
                  className="w-full px-3 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                />
              </div>
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Pod</label>
                <select
                  value={empModal.data.pod_id}
                  onChange={(e) =>
                    setEmpModal({ ...empModal, data: { ...empModal.data, pod_id: e.target.value } })
                  }
                  className="w-full px-3 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                >
                  {pods.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Default Weekly Off</label>
                <select
                  value={empModal.data.default_weekly_off}
                  onChange={(e) =>
                    setEmpModal({
                      ...empModal,
                      data: { ...empModal.data, default_weekly_off: Number(e.target.value) },
                    })
                  }
                  className="w-full px-3 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                >
                  {WEEKDAY_LABELS.map((lbl, idx) => (
                    <option key={idx} value={idx}>
                      {idx} — {lbl}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Preferred Weekly Off</label>
                <select
                  value={empModal.data.preferred_weekly_off}
                  onChange={(e) =>
                    setEmpModal({
                      ...empModal,
                      data: { ...empModal.data, preferred_weekly_off: Number(e.target.value) },
                    })
                  }
                  className="w-full px-3 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                >
                  {WEEKDAY_LABELS.map((lbl, idx) => (
                    <option key={idx} value={idx}>
                      {idx} — {lbl}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Role</label>
                <select
                  value={empModal.data.role}
                  onChange={(e) =>
                    setEmpModal({ ...empModal, data: { ...empModal.data, role: e.target.value } })
                  }
                  className="w-full px-3 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                >
                  <option value="ASSOCIATE">ASSOCIATE</option>
                  <option value="POD_LEAD">POD_LEAD</option>
                </select>
              </div>
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Off Rule</label>
                <select
                  value={empModal.data.weekly_off_rule}
                  onChange={(e) =>
                    setEmpModal({
                      ...empModal,
                      data: { ...empModal.data, weekly_off_rule: e.target.value },
                    })
                  }
                  className="w-full px-3 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                >
                  <option value="FIXED">FIXED</option>
                  <option value="ROTATIONAL">ROTATIONAL</option>
                </select>
              </div>
              <div className="col-span-2 flex items-center gap-4 pt-1">
                <label className="inline-flex items-center gap-2 font-medium text-slate-700">
                  <input
                    type="checkbox"
                    checked={empModal.data.is_floater}
                    onChange={(e) =>
                      setEmpModal({
                        ...empModal,
                        data: { ...empModal.data, is_floater: e.target.checked },
                      })
                    }
                  />
                  Floater
                </label>
                <label className="inline-flex items-center gap-2 font-medium text-slate-700">
                  <input
                    type="checkbox"
                    checked={empModal.data.active}
                    onChange={(e) =>
                      setEmpModal({
                        ...empModal,
                        data: { ...empModal.data, active: e.target.checked },
                      })
                    }
                  />
                  Active
                </label>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setEmpModal(null)}
                className="px-3 py-2 rounded-lg border border-neutral-200 text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={busy}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-neutral-900 text-white text-xs font-semibold disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                {busy ? (empModal.mode === "add" ? "Creating..." : "Saving...") : "Save Employee"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Brand Modal */}
      {brandModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              runAction(
                () =>
                  brandModal.mode === "add"
                    ? createBrand(brandModal.data).then(() => undefined)
                    : updateBrand(brandModal.data.id, brandModal.data).then(() => undefined),
                `${brandModal.mode === "add" ? "Created" : "Updated"} brand ${brandModal.data.id}`
              ).then(() => setBrandModal(null));
            }}
            className="bg-white border border-neutral-200 rounded-2xl shadow-xl w-full max-w-md p-5 space-y-4"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate-900">
                {brandModal.mode === "add" ? "Add Brand" : `Edit Brand ${brandModal.data.id}`}
              </h3>
              <button type="button" onClick={() => setBrandModal(null)}>
                <X className="w-4 h-4 text-slate-400" />
              </button>
            </div>
            <div className="space-y-3 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Brand ID</label>
                <input
                  type="text"
                  required
                  disabled={brandModal.mode === "edit"}
                  value={brandModal.data.id}
                  onChange={(e) =>
                    setBrandModal({ ...brandModal, data: { ...brandModal.data, id: e.target.value } })
                  }
                  className="w-full px-3 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                />
              </div>
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Brand Name</label>
                <input
                  type="text"
                  required
                  value={brandModal.data.name}
                  onChange={(e) =>
                    setBrandModal({
                      ...brandModal,
                      data: { ...brandModal.data, name: e.target.value },
                    })
                  }
                  className="w-full px-3 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Pod</label>
                  <select
                    value={brandModal.data.pod_id}
                    onChange={(e) =>
                      setBrandModal({
                        ...brandModal,
                        data: { ...brandModal.data, pod_id: e.target.value },
                      })
                    }
                    className="w-full px-3 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                  >
                    {pods.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Staffing Model</label>
                  <select
                    value={brandModal.data.staffing_model}
                    onChange={(e) =>
                      setBrandModal({
                        ...brandModal,
                        data: { ...brandModal.data, staffing_model: e.target.value },
                      })
                    }
                    className="w-full px-3 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                  >
                    <option value="SINGLE_RESOURCE">SINGLE_RESOURCE</option>
                    <option value="MULTI_RESOURCE">MULTI_RESOURCE</option>
                  </select>
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setBrandModal(null)}
                className="px-3 py-2 rounded-lg border border-neutral-200 text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={busy}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-neutral-900 text-white text-xs font-semibold disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                {busy ? (brandModal.mode === "add" ? "Creating..." : "Saving...") : "Save Brand"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Rule Modal */}
      {ruleModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              let parsedOverrides: Record<string, number> = {};
              try {
                parsedOverrides = JSON.parse(ruleModal.overridesText || "{}");
              } catch {
                setErrorMsg("Day overrides must be valid JSON (e.g. {\"0\": 2})");
                return;
              }
              const payload = {
                ...ruleModal.data,
                day_min_staffing_overrides: parsedOverrides,
              };
              runAction(
                () =>
                  ruleModal.mode === "add"
                    ? createRule(payload).then(() => undefined)
                    : updateRule(payload.id, payload).then(() => undefined),
                `${ruleModal.mode === "add" ? "Created" : "Updated"} rule ${payload.id}`
              ).then(() => setRuleModal(null));
            }}
            className="bg-white border border-neutral-200 rounded-2xl shadow-xl w-full max-w-md p-5 space-y-4"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate-900">
                {ruleModal.mode === "add"
                  ? "Add Operating Rule"
                  : `Edit Rule ${ruleModal.data.id}`}
              </h3>
              <button type="button" onClick={() => setRuleModal(null)}>
                <X className="w-4 h-4 text-slate-400" />
              </button>
            </div>
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Brand</label>
                  <select
                    value={ruleModal.data.brand_id}
                    onChange={(e) =>
                      setRuleModal({
                        ...ruleModal,
                        data: { ...ruleModal.data, brand_id: e.target.value },
                      })
                    }
                    className="w-full px-2.5 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                  >
                    {brands.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Process</label>
                  <select
                    value={ruleModal.data.process_id}
                    onChange={(e) =>
                      setRuleModal({
                        ...ruleModal,
                        data: { ...ruleModal.data, process_id: e.target.value },
                      })
                    }
                    className="w-full px-2.5 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                  >
                    {processes.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.code} — {p.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Calendar Type</label>
                  <select
                    value={ruleModal.data.calendar_type}
                    onChange={(e) =>
                      setRuleModal({
                        ...ruleModal,
                        data: { ...ruleModal.data, calendar_type: e.target.value },
                      })
                    }
                    className="w-full px-2.5 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                  >
                    <option value="365_DAYS">365_DAYS</option>
                    <option value="DAILY_EXCEPT_PH">DAILY_EXCEPT_PH</option>
                    <option value="MON_SAT_EXCEPT_PH">MON_SAT_EXCEPT_PH</option>
                  </select>
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Min Staffing</label>
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={ruleModal.data.min_staffing}
                    onChange={(e) =>
                      setRuleModal({
                        ...ruleModal,
                        data: { ...ruleModal.data, min_staffing: Number(e.target.value) },
                      })
                    }
                    className="w-full px-2.5 py-2 border border-neutral-200 rounded-lg bg-neutral-50"
                  />
                </div>
              </div>
              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  Day Min Staffing Overrides (JSON, 0=Mon..6=Sun)
                </label>
                <input
                  type="text"
                  value={ruleModal.overridesText}
                  onChange={(e) => setRuleModal({ ...ruleModal, overridesText: e.target.value })}
                  placeholder='{"0": 2}'
                  className="w-full px-2.5 py-2 border border-neutral-200 rounded-lg bg-neutral-50 font-mono"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setRuleModal(null)}
                className="px-3 py-2 rounded-lg border border-neutral-200 text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={busy}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-neutral-900 text-white text-xs font-semibold disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                {busy ? (ruleModal.mode === "add" ? "Creating..." : "Saving...") : "Save Rule"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
