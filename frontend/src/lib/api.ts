export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

// ─── Entity Interfaces ────────────────────────────────────────────────────────

export interface Pod {
  id: string;
  name: string;
  lead_employee_id: string;
  color?: string | null;
}

export const POD_COLOR_OPTIONS = [
  { key: "rose", label: "Rose", swatch: "bg-rose-500", dot: "bg-rose-500", borderTop: "border-t-rose-500", borderLeft: "border-l-rose-500", headerBg: "bg-rose-50/60", badge: "bg-rose-50 text-rose-700 border-rose-200" },
  { key: "sky", label: "Sky", swatch: "bg-sky-500", dot: "bg-sky-500", borderTop: "border-t-sky-500", borderLeft: "border-l-sky-500", headerBg: "bg-sky-50/60", badge: "bg-sky-50 text-sky-700 border-sky-200" },
  { key: "emerald", label: "Emerald", swatch: "bg-emerald-500", dot: "bg-emerald-500", borderTop: "border-t-emerald-500", borderLeft: "border-l-emerald-500", headerBg: "bg-emerald-50/60", badge: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  { key: "amber", label: "Amber", swatch: "bg-amber-500", dot: "bg-amber-500", borderTop: "border-t-amber-500", borderLeft: "border-l-amber-500", headerBg: "bg-amber-50/60", badge: "bg-amber-50 text-amber-700 border-amber-200" },
  { key: "violet", label: "Violet", swatch: "bg-violet-500", dot: "bg-violet-500", borderTop: "border-t-violet-500", borderLeft: "border-l-violet-500", headerBg: "bg-violet-50/60", badge: "bg-violet-50 text-violet-700 border-violet-200" },
  { key: "teal", label: "Teal", swatch: "bg-teal-500", dot: "bg-teal-500", borderTop: "border-t-teal-500", borderLeft: "border-l-teal-500", headerBg: "bg-teal-50/60", badge: "bg-teal-50 text-teal-700 border-teal-200" },
  { key: "blue", label: "Blue", swatch: "bg-blue-600", dot: "bg-blue-600", borderTop: "border-t-blue-600", borderLeft: "border-l-blue-600", headerBg: "bg-blue-50/60", badge: "bg-blue-50 text-blue-700 border-blue-200" },
  { key: "orange", label: "Orange", swatch: "bg-orange-500", dot: "bg-orange-500", borderTop: "border-t-orange-500", borderLeft: "border-l-orange-500", headerBg: "bg-orange-50/60", badge: "bg-orange-50 text-orange-700 border-orange-200" },
] as const;

export function getPodColorTheme(color?: string | null, fallbackIdx: number = 0) {
  return (
    POD_COLOR_OPTIONS.find((c) => c.key === color) ||
    POD_COLOR_OPTIONS[fallbackIdx % 4]
  );
}

export interface Process {
  id: string;
  code: string;
  name: string;
  description?: string | null;
}

export interface Employee {
  id: string;
  name: string;
  email: string;
  role: string; // POD_LEAD | ASSOCIATE
  pod_id: string;
  skills: string[];
  default_weekly_off: number; // 0=Mon .. 6=Sun
  preferred_weekly_off: number; // 0=Mon .. 6=Sun
  weekly_off_rule: string; // FIXED | ROTATIONAL
  shift: string;
  is_floater: boolean;
  active: boolean;
}

export interface Brand {
  id: string;
  name: string;
  pod_id: string;
  tier: string;
  staffing_model: string; // SINGLE_RESOURCE | MULTI_RESOURCE
}

export interface BrandProcessRule {
  id: string;
  brand_id: string;
  process_id: string;
  calendar_type: string; // 365_DAYS | DAILY_EXCEPT_PH | MON_SAT_EXCEPT_PH
  min_staffing: number;
  day_min_staffing_overrides: Record<string, number>;
}

export interface Allocation {
  id: string;
  employee_id: string;
  brand_id: string;
  process_id: string;
  allocation_type: string; // PRIMARY | BACKUP
}

export interface PublicHoliday {
  id: string;
  date: string; // YYYY-MM-DD
  name: string;
  is_national: boolean;
}

export interface LeaveAndCompOff {
  id: string;
  employee_id: string;
  start_date: string; // YYYY-MM-DD
  end_date: string; // YYYY-MM-DD
  type: string; // PLANNED_LEAVE | COMP_OFF
  status: string; // PENDING | APPROVED | REJECTED
  reason?: string | null;
}

// ─── Roster Interfaces ────────────────────────────────────────────────────────

export interface KPIStats {
  total_employees: number;
  total_operating_slots: number;
  covered_slots: number;
  uncovered_slots: number;
  understaffed_slots: number;
  coverage_percentage: number;
  hard_conflicts_count: number;
  soft_conflicts_count: number;
}

export interface SuggestedResolution {
  employee_id: string;
  name: string;
  score: number;
  tier: string;
  reason: string;
}

export interface Conflict {
  date: string;
  severity: "HARD" | "SOFT";
  conflict_type: string;
  brand_id?: string | null;
  brand_name?: string | null;
  process_id?: string | null;
  process_name?: string | null;
  employee_id?: string | null;
  employee_name?: string | null;
  message: string;
  suggested_resolutions: SuggestedResolution[];
  resolved: boolean;
}

export type ConflictDTO = Conflict;

export type CoverageStatusType =
  | "COVERED"
  | "BACKUP_COVERED"
  | "UNDERSTAFFED"
  | "UNCOVERED"
  | "NOT_OPERATING";

export interface DailyCoverage {
  date: string;
  brand_id: string;
  brand_name: string;
  process_id: string;
  process_code: string;
  calendar_type: string;
  is_operating: boolean;
  required_staffing: number;
  working_count: number;
  status: CoverageStatusType;
  assigned_employee_ids: string[];
  backup_employee_ids: string[];
}

export type DailyCoverageDTO = DailyCoverage;

export type EmployeeStatusType =
  | "WORKING"
  | "WEEKLY_OFF"
  | "PUBLIC_HOLIDAY"
  | "PLANNED_LEAVE"
  | "COMP_OFF"
  | "BACKUP_COVERAGE";

export interface RosterEntry {
  employee_id: string;
  date: string;
  status: EmployeeStatusType;
  assigned_brand_id?: string | null;
  assigned_process_id?: string | null;
  is_manual_override: boolean;
  notes?: string | null;
}

export type RosterEntryDTO = RosterEntry;

export interface MonthlyRosterResponse {
  month: string;
  roster_id: string;
  status: string;
  generated_at: string;
  kpis: KPIStats;
  entries: RosterEntry[];
  coverage_matrix: DailyCoverage[];
  conflicts: Conflict[];
}

export type RosterViewType = "company" | "pod" | "brand" | "process" | "employee";

export interface PatchRosterEntryPayload {
  employee_id: string;
  date: string;
  status: EmployeeStatusType;
  assigned_brand_id?: string | null;
  assigned_process_id?: string | null;
  notes?: string | null;
}

export interface AssignBackupPayload {
  date: string;
  brand_id: string;
  process_id: string;
  employee_id: string;
  notes?: string | null;
}

export interface LeaveApprovalImpact {
  hard_conflicts_before: number;
  hard_conflicts_after: number;
  new_conflicts: Conflict[];
  affected_brands: string[];
}

export interface LeaveApprovalResponse {
  leave?: LeaveAndCompOff;
  impact?: LeaveApprovalImpact;
  message?: string;
  impact_summary?: string;
  new_hard_conflicts_count?: number;
  roster?: MonthlyRosterResponse;
  conflicts?: Conflict[];
  kpis?: KPIStats;
}

export type PlanStrategy = "COVERAGE_FIRST" | "PREFERENCE_FIRST" | "BALANCED";

export interface PlanComparisonItem {
  strategy: PlanStrategy;
  label?: string;
  description?: string;
  coverage_percentage: number;
  covered_slots: number;
  total_operating_slots?: number;
  hard_conflicts_count: number;
  soft_conflicts_count: number;
}

export interface ComparePlansResponse {
  month: string;
  plans: PlanComparisonItem[];
}

export type PublishRosterResponse =
  | { requiresForce: false; roster: MonthlyRosterResponse }
  | { requiresForce: true; hardConflictsCount: number; detail: string };

export interface NotificationItem {
  id: string;
  month?: string;
  title?: string;
  message: string;
  created_at: string;
  read: boolean;
  actor?: string;
  action_type?: string;
}

export interface ExplainConflictResponse {
  explanation: string;
  action_steps: string[];
  provider: string;
}

export interface AutoResolveResponse {
  resolved_count: number;
  remaining_hard_conflicts: number;
  coverage_before: number;
  coverage_after: number;
  structural_gaps_summary: string;
  roster: MonthlyRosterResponse;
}

export interface LeaveImpactPreviewResponse {
  hard_conflicts_before: number;
  hard_conflicts_after: number;
  new_hard_conflicts_count: number;
  coverage_before: number;
  coverage_after: number;
  affected_dates: string[];
  affected_brands: { brand_id: string; brand_name: string }[];
  affected_processes: string[];
  new_conflicts: Conflict[];
}

export interface BottleneckPodItem {
  pod_id: string;
  pod_name: string;
  hard_conflicts_count: number;
}

export interface BottleneckBrandItem {
  brand_id: string;
  brand_name: string;
  pod_id: string;
  hard_conflicts_count: number;
}

export interface BottlenecksResponse {
  total_hard_conflicts: number;
  top_pods: BottleneckPodItem[];
  top_brands: BottleneckBrandItem[];
  recommendations: string[];
}

// ─── HTTP Helper ──────────────────────────────────────────────────────────────

function formatApiError(detail: unknown, fallback: string): string {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const obj = item as { loc?: unknown[]; msg?: string };
          const loc = Array.isArray(obj.loc) ? obj.loc.slice(1).join(".") : "";
          return loc ? `${loc}: ${obj.msg || "Invalid value"}` : obj.msg || JSON.stringify(item);
        }
        return String(item);
      })
      .filter(Boolean);
    return msgs.length > 0 ? msgs.join("; ") : fallback;
  }
  if (typeof detail === "object") {
    const maybeMsg = (detail as { message?: string; detail?: string }).message || (detail as { detail?: string }).detail;
    return maybeMsg || JSON.stringify(detail);
  }
  return String(detail);
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {}),
    },
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const err = new Error(
      formatApiError(errorData.detail, `Request failed (${res.status}): ${res.statusText}`)
    ) as Error & {
      status?: number;
    };
    err.status = res.status;
    throw err;
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return res.json();
}

// ─── Health & Admin ───────────────────────────────────────────────────────────

export async function fetchHealth(): Promise<{ status: string; service: string }> {
  return request("/api/health");
}

export const checkBackendHealth = fetchHealth;

export async function resetSeedData(): Promise<{ status: string; message?: string }> {
  return request("/api/admin/reset-seed", { method: "POST" });
}

// ─── Roster Endpoints ─────────────────────────────────────────────────────────

export async function fetchMonthlyRoster(
  month: string = "2026-12",
  view?: RosterViewType,
  filterId?: string
): Promise<MonthlyRosterResponse> {
  const params = new URLSearchParams();
  if (view) params.set("view", view);
  if (filterId) params.set("filter_id", filterId);
  const qs = params.toString();
  return request(`/api/rosters/${encodeURIComponent(month)}${qs ? `?${qs}` : ""}`);
}

export async function generateMonthlyRoster(month: string = "2026-12"): Promise<MonthlyRosterResponse> {
  return request(`/api/rosters/generate?month=${encodeURIComponent(month)}`, {
    method: "POST",
  });
}

export async function patchRosterEntry(
  month: string,
  payload: PatchRosterEntryPayload
): Promise<MonthlyRosterResponse> {
  return request(`/api/rosters/${encodeURIComponent(month)}/entry`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function assignBackup(
  month: string,
  payload: AssignBackupPayload
): Promise<MonthlyRosterResponse> {
  return request(`/api/rosters/${encodeURIComponent(month)}/assign-backup`, {
    method: "POST",
    body: JSON.stringify({
      date: payload.date,
      brand_id: payload.brand_id,
      process_id: payload.process_id,
      backup_employee_id: payload.employee_id,
    }),
  });
}

export function getCsvExportUrl(month: string = "2026-12"): string {
  return `${API_BASE_URL}/api/rosters/${encodeURIComponent(month)}/export.csv`;
}

export function getExcelExportUrl(month: string = "2026-12"): string {
  return `${API_BASE_URL}/api/rosters/${encodeURIComponent(month)}/export.xlsx`;
}

interface RawPlanItem {
  strategy: PlanStrategy;
  label?: string;
  description?: string;
  kpis?: KPIStats;
  coverage_percentage?: number;
  covered_slots?: number;
  total_operating_slots?: number;
  hard_conflicts_count?: number;
  soft_conflicts_count?: number;
}

export async function comparePlans(month: string): Promise<ComparePlansResponse> {
  const data = await request<{ month?: string; plans?: RawPlanItem[] } | RawPlanItem[]>(
    `/api/rosters/${encodeURIComponent(month)}/compare-plans`,
    { method: "POST" }
  );
  const rawPlans = Array.isArray(data) ? data : data.plans || [];
  const plans: PlanComparisonItem[] = rawPlans.map((p) => ({
    strategy: p.strategy,
    label: p.label,
    description: p.description,
    coverage_percentage: p.kpis?.coverage_percentage ?? p.coverage_percentage ?? 0,
    covered_slots: p.kpis?.covered_slots ?? p.covered_slots ?? 0,
    total_operating_slots: p.kpis?.total_operating_slots ?? p.total_operating_slots ?? 0,
    hard_conflicts_count: p.kpis?.hard_conflicts_count ?? p.hard_conflicts_count ?? 0,
    soft_conflicts_count: p.kpis?.soft_conflicts_count ?? p.soft_conflicts_count ?? 0,
  }));
  return { month, plans };
}

export async function applyPlan(
  month: string,
  strategy: PlanStrategy
): Promise<MonthlyRosterResponse> {
  return request(
    `/api/rosters/${encodeURIComponent(month)}/apply-plan?strategy=${encodeURIComponent(strategy)}`,
    { method: "POST" }
  );
}

export async function approvePodRoster(month: string): Promise<MonthlyRosterResponse> {
  return request(`/api/rosters/${encodeURIComponent(month)}/approve-pod`, {
    method: "POST",
  });
}

export async function publishRoster(
  month: string,
  force: boolean = false
): Promise<PublishRosterResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/rosters/${encodeURIComponent(month)}/publish`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force, actor_role: "OPS_MANAGER" }),
    }
  );

  if (res.status === 409) {
    const errorData = await res.json().catch(() => ({}));
    return {
      requiresForce: true,
      hardConflictsCount:
        typeof errorData.hard_conflicts_count === "number"
          ? errorData.hard_conflicts_count
          : 1,
      detail:
        formatApiError(
          errorData.detail,
          "Roster has unresolved HARD conflicts. Override required to publish."
        ),
    };
  }

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const err = new Error(
      formatApiError(errorData.detail, `Request failed (${res.status}): ${res.statusText}`)
    ) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }

  const roster = (await res.json()) as MonthlyRosterResponse;
  return { requiresForce: false, roster };
}

interface RawNotification {
  id: number | string;
  month?: string;
  event_type?: string;
  action_type?: string;
  title?: string;
  message: string;
  actor_role?: string;
  actor?: string;
  created_at: string;
  is_read?: boolean;
  read?: boolean;
}

export async function fetchNotifications(month: string): Promise<NotificationItem[]> {
  const data = await request<RawNotification[] | { notifications: RawNotification[] }>(
    `/api/notifications?month=${encodeURIComponent(month)}`
  );
  const rawList = Array.isArray(data) ? data : data.notifications || [];
  return rawList.map((n) => ({
    id: String(n.id),
    month: n.month,
    title: n.title || (n.event_type ? n.event_type.replace(/_/g, " ") : "Roster Update"),
    message: n.message,
    created_at: n.created_at,
    read: typeof n.is_read === "boolean" ? n.is_read : Boolean(n.read),
    actor: n.actor || n.actor_role,
    action_type: n.action_type || n.event_type,
  }));
}

export async function markNotificationsRead(): Promise<{ status?: string }> {
  return request("/api/notifications/mark-read", { method: "POST" });
}

function buildClientDeterministicFallback(conflict: Conflict): ExplainConflictResponse {
  const brandLabel = conflict.brand_name || conflict.brand_id || "the affected brand";
  const procLabel = conflict.process_name || conflict.process_id || "operations";
  const top = conflict.suggested_resolutions?.[0];
  const steps: string[] = [];
  if (top) {
    steps.push(`Assign top-ranked backup ${top.name} (score ${top.score}: ${top.reason}) for ${conflict.date}.`);
  } else {
    steps.push(`Review pod capacity for ${brandLabel} on ${conflict.date} and reassign an available floater or Pod Lead.`);
  }
  if ((conflict.suggested_resolutions?.length || 0) > 1) {
    const alt = conflict.suggested_resolutions[1];
    steps.push(`Keep ${alt.name} on standby as secondary coverage.`);
  }
  steps.push(`Verify ${brandLabel} (${procLabel}) coverage status updates to COVERED/BACKUP_COVERED.`);
  return {
    explanation: `On ${conflict.date}, ${brandLabel} (${procLabel}) has a ${conflict.severity.toLowerCase()} conflict. ${conflict.message}`,
    action_steps: steps.slice(0, 3),
    provider: "Deterministic Fallback",
  };
}

export async function explainConflict(
  month: string,
  conflict: Conflict
): Promise<ExplainConflictResponse> {
  // Send only the fields the backend ExplainConflictRequest expects
  const payload = {
    date: conflict.date,
    conflict_type: conflict.conflict_type,
    severity: conflict.severity,
    brand_id: conflict.brand_id ?? null,
    brand_name: conflict.brand_name ?? null,
    process_id: conflict.process_id ?? null,
    process_name: conflict.process_name ?? null,
    employee_name: conflict.employee_name ?? null,
    message: conflict.message,
    suggested_resolutions: (conflict.suggested_resolutions || []).map((r) => ({
      employee_id: r.employee_id,
      name: r.name,
      score: r.score,
      tier: r.tier,
      reason: r.reason,
    })),
  };

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 9000);
  try {
    return await request(`/api/rosters/${encodeURIComponent(month)}/explain-conflict`, {
      method: "POST",
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") {
      return buildClientDeterministicFallback(conflict);
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function autoResolveGaps(
  month: string,
  minScore: number = 70
): Promise<AutoResolveResponse> {
  return request(`/api/rosters/${encodeURIComponent(month)}/auto-resolve?min_score=${minScore}`, {
    method: "POST",
  });
}

export async function fetchBottlenecks(month: string): Promise<BottlenecksResponse> {
  return request(`/api/rosters/${encodeURIComponent(month)}/bottlenecks`);
}

// ─── Pods CRUD ────────────────────────────────────────────────────────────────

export const fetchPods = (): Promise<Pod[]> => request("/api/pods");
export const createPod = (data: Pod): Promise<Pod> =>
  request("/api/pods", { method: "POST", body: JSON.stringify(data) });
export const updatePod = (id: string, data: Partial<Pod>): Promise<Pod> =>
  request(`/api/pods/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(data) });
export const deletePod = (id: string): Promise<void> =>
  request(`/api/pods/${encodeURIComponent(id)}`, { method: "DELETE" });

// ─── Processes CRUD ───────────────────────────────────────────────────────────

export const fetchProcesses = (): Promise<Process[]> => request("/api/processes");
export const createProcess = (data: Process): Promise<Process> =>
  request("/api/processes", { method: "POST", body: JSON.stringify(data) });
export const updateProcess = (id: string, data: Partial<Process>): Promise<Process> =>
  request(`/api/processes/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(data) });
export const deleteProcess = (id: string): Promise<void> =>
  request(`/api/processes/${encodeURIComponent(id)}`, { method: "DELETE" });

// ─── Employees CRUD ───────────────────────────────────────────────────────────

export const fetchEmployees = (): Promise<Employee[]> => request("/api/employees");
export const createEmployee = (data: Employee): Promise<Employee> =>
  request("/api/employees", { method: "POST", body: JSON.stringify(data) });
export const updateEmployee = (id: string, data: Partial<Employee>): Promise<Employee> =>
  request(`/api/employees/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(data) });
export const deleteEmployee = (id: string): Promise<void> =>
  request(`/api/employees/${encodeURIComponent(id)}`, { method: "DELETE" });

// ─── Brands CRUD ──────────────────────────────────────────────────────────────

export const fetchBrands = (): Promise<Brand[]> => request("/api/brands");
export const createBrand = (data: Brand): Promise<Brand> =>
  request("/api/brands", { method: "POST", body: JSON.stringify(data) });
export const updateBrand = (id: string, data: Partial<Brand>): Promise<Brand> =>
  request(`/api/brands/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(data) });
export const deleteBrand = (id: string): Promise<void> =>
  request(`/api/brands/${encodeURIComponent(id)}`, { method: "DELETE" });

// ─── Brand Process Rules CRUD ─────────────────────────────────────────────────

export const fetchRules = (): Promise<BrandProcessRule[]> => request("/api/rules");
export const createRule = (data: BrandProcessRule): Promise<BrandProcessRule> =>
  request("/api/rules", { method: "POST", body: JSON.stringify(data) });
export const updateRule = (id: string, data: Partial<BrandProcessRule>): Promise<BrandProcessRule> =>
  request(`/api/rules/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(data) });
export const deleteRule = (id: string): Promise<void> =>
  request(`/api/rules/${encodeURIComponent(id)}`, { method: "DELETE" });

// ─── Allocations CRUD ─────────────────────────────────────────────────────────

export const fetchAllocations = (): Promise<Allocation[]> => request("/api/allocations");
export const createAllocation = (data: Allocation): Promise<Allocation> =>
  request("/api/allocations", { method: "POST", body: JSON.stringify(data) });
export const deleteAllocation = (id: string): Promise<void> =>
  request(`/api/allocations/${encodeURIComponent(id)}`, { method: "DELETE" });

// ─── Public Holidays CRUD ─────────────────────────────────────────────────────

export const fetchHolidays = (): Promise<PublicHoliday[]> => request("/api/holidays");
export const createHoliday = (data: PublicHoliday): Promise<PublicHoliday> =>
  request("/api/holidays", { method: "POST", body: JSON.stringify(data) });
export const deleteHoliday = (id: string): Promise<void> =>
  request(`/api/holidays/${encodeURIComponent(id)}`, { method: "DELETE" });

// ─── Leaves & Comp-Offs CRUD + Approval ───────────────────────────────────────

export const fetchLeaves = (): Promise<LeaveAndCompOff[]> => request("/api/leaves");
export const createLeave = (data: LeaveAndCompOff): Promise<LeaveAndCompOff> =>
  request("/api/leaves", { method: "POST", body: JSON.stringify(data) });
export const deleteLeave = (id: string): Promise<void> =>
  request(`/api/leaves/${encodeURIComponent(id)}`, { method: "DELETE" });
export const approveLeave = (leaveId: string, month: string = "2026-12"): Promise<LeaveApprovalResponse> =>
  request(`/api/leaves/${encodeURIComponent(leaveId)}/approve?month=${encodeURIComponent(month)}`, {
    method: "POST",
  });
export const rejectLeave = (leaveId: string): Promise<LeaveAndCompOff> =>
  request(`/api/leaves/${encodeURIComponent(leaveId)}/reject`, {
    method: "POST",
  });
export const previewLeaveImpact = (
  leaveId: string,
  month: string = "2026-12"
): Promise<LeaveImpactPreviewResponse> =>
  request(`/api/leaves/${encodeURIComponent(leaveId)}/preview-impact?month=${encodeURIComponent(month)}`, {
    method: "POST",
  });
export const previewAdhocLeaveImpact = (
  payload: { employee_id: string; start_date: string; end_date: string; type?: string },
  month: string = "2026-12"
): Promise<LeaveImpactPreviewResponse> =>
  request(`/api/leaves/preview-impact?month=${encodeURIComponent(month)}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
