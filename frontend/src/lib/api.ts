const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface SuggestedResolution {
  employee_id: string;
  name: string;
  score: number;
  tier: string;
  reason: string;
}

export interface ConflictDTO {
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

export type Conflict = ConflictDTO;

export interface DailyCoverageDTO {
  date: string;
  brand_id: string;
  brand_name: string;
  process_id: string;
  process_code: string;
  calendar_type: string;
  is_operating: boolean;
  required_staffing: number;
  working_count: number;
  status: "COVERED" | "BACKUP_COVERED" | "UNDERSTAFFED" | "UNCOVERED" | "NOT_OPERATING";
  assigned_employee_ids: string[];
  backup_employee_ids: string[];
}

export interface RosterEntryDTO {
  employee_id: string;
  date: string;
  status: "WORKING" | "WEEKLY_OFF" | "PUBLIC_HOLIDAY" | "PLANNED_LEAVE" | "COMP_OFF" | "BACKUP_COVERAGE";
  assigned_brand_id?: string | null;
  assigned_process_id?: string | null;
  is_manual_override: boolean;
  notes?: string | null;
}

export type RosterEntry = RosterEntryDTO;

export interface MonthlyRosterResponse {
  month: string;
  roster_id: string;
  status: string;
  generated_at: string;
  kpis: {
    total_employees: number;
    total_operating_slots: number;
    covered_slots: number;
    uncovered_slots: number;
    understaffed_slots: number;
    coverage_percentage: number;
    hard_conflicts_count: number;
    soft_conflicts_count: number;
  };
  entries: RosterEntryDTO[];
  coverage_matrix: DailyCoverageDTO[];
  conflicts: ConflictDTO[];
}

export async function generateMonthlyRoster(month: string = "2026-12"): Promise<MonthlyRosterResponse> {
  const res = await fetch(`${API_BASE_URL}/api/rosters/generate?month=${encodeURIComponent(month)}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
  });
  if (!res.ok) {
    const errorBody = await res.text();
    throw new Error(`Failed to generate roster: ${res.status} ${res.statusText} - ${errorBody}`);
  }
  return res.json();
}

export async function fetchHealth(): Promise<{ status: string; service: string }> {
  const res = await fetch(`${API_BASE_URL}/api/health`);
  if (!res.ok) {
    throw new Error(`Backend health check failed: ${res.statusText}`);
  }
  return res.json();
}

export const checkBackendHealth = fetchHealth;
