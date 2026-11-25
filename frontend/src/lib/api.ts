export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

// ─── Entity Interfaces ────────────────────────────────────────────────────────

export interface Pod {
  id: string;
  name: string;
  lead_employee_id: string;
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

export interface LeaveApprovalResponse {
  leave?: LeaveAndCompOff;
  message?: string;
  impact_summary?: string;
  new_hard_conflicts_count?: number;
  roster?: MonthlyRosterResponse;
  conflicts?: Conflict[];
  kpis?: KPIStats;
}

// ─── HTTP Helper ──────────────────────────────────────────────────────────────

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
    const err = new Error(errorData.detail || `Request failed (${res.status}): ${res.statusText}`) as Error & {
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
    body: JSON.stringify(payload),
  });
}

export function getCsvExportUrl(month: string = "2026-12"): string {
  return `${API_BASE_URL}/api/rosters/${encodeURIComponent(month)}/export.csv`;
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
