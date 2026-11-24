from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# Status constants
class EmployeeStatus:
    WORKING = "WORKING"
    WEEKLY_OFF = "WEEKLY_OFF"
    PUBLIC_HOLIDAY = "PUBLIC_HOLIDAY"
    PLANNED_LEAVE = "PLANNED_LEAVE"
    COMP_OFF = "COMP_OFF"
    BACKUP_COVERAGE = "BACKUP_COVERAGE"


class CoverageStatus:
    COVERED = "COVERED"
    BACKUP_COVERED = "BACKUP_COVERED"
    UNDERSTAFFED = "UNDERSTAFFED"
    UNCOVERED = "UNCOVERED"
    NOT_OPERATING = "NOT_OPERATING"


class ConflictSeverity:
    HARD = "HARD"
    SOFT = "SOFT"


class ConflictType:
    UNCOVERED_BRAND_PROCESS = "UNCOVERED_BRAND_PROCESS"
    INSUFFICIENT_STAFFING = "INSUFFICIENT_STAFFING"
    MULTI_BRAND_CASCADE = "MULTI_BRAND_CASCADE"
    LEAVE_OR_OFF_VIOLATION = "LEAVE_OR_OFF_VIOLATION"
    SHIFT_OR_OVERLOAD_CONFLICT = "SHIFT_OR_OVERLOAD_CONFLICT"
    PREFERENCE_VIOLATED = "PREFERENCE_VIOLATED"


# DTO Schemas
class SuggestedResolution(BaseModel):
    employee_id: str
    name: str
    score: int
    tier: str  # SAME_POD_FLOATER, SAME_POD_SURPLUS, CROSS_POD_FLOATER, POD_LEAD_ESCALATION
    reason: str


class ConflictDTO(BaseModel):
    date: str
    severity: str
    conflict_type: str
    brand_id: Optional[str] = None
    brand_name: Optional[str] = None
    process_id: Optional[str] = None
    process_name: Optional[str] = None
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    message: str
    suggested_resolutions: List[SuggestedResolution] = []
    resolved: bool = False


class DailyCoverageDTO(BaseModel):
    date: str
    brand_id: str
    brand_name: str
    process_id: str
    process_code: str
    calendar_type: str
    is_operating: bool
    required_staffing: int
    working_count: int
    status: str  # COVERED, BACKUP_COVERED, UNDERSTAFFED, UNCOVERED, NOT_OPERATING
    assigned_employee_ids: List[str] = []
    backup_employee_ids: List[str] = []


class RosterEntryDTO(BaseModel):
    employee_id: str
    date: str
    status: str
    assigned_brand_id: Optional[str] = None
    assigned_process_id: Optional[str] = None
    is_manual_override: bool = False
    notes: Optional[str] = None


class MonthlyRosterResponse(BaseModel):
    month: str
    roster_id: str
    status: str
    generated_at: str
    kpis: Dict[str, Any]
    entries: List[RosterEntryDTO]
    coverage_matrix: List[DailyCoverageDTO]
    conflicts: List[ConflictDTO]
