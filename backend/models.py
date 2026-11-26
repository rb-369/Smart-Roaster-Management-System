from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import JSON


class Pod(SQLModel, table=True):
    __tablename__ = "pods"
    id: str = Field(primary_key=True)
    name: str
    lead_employee_id: str
    color: Optional[str] = None


class Process(SQLModel, table=True):
    __tablename__ = "processes"
    id: str = Field(primary_key=True)
    code: str
    name: str
    description: Optional[str] = None


class Employee(SQLModel, table=True):
    __tablename__ = "employees"
    id: str = Field(primary_key=True)
    name: str
    email: str
    role: str  # POD_LEAD, ASSOCIATE
    pod_id: str = Field(foreign_key="pods.id")
    skills: List[str] = Field(default=[], sa_column=Column(JSON))
    default_weekly_off: int = 6  # 0=Mon, 6=Sun
    preferred_weekly_off: int = 6
    weekly_off_rule: str = "FIXED"  # FIXED, ROTATIONAL
    shift: str = "DAY_9_18"
    is_floater: bool = False
    active: bool = True


class Brand(SQLModel, table=True):
    __tablename__ = "brands"
    id: str = Field(primary_key=True)
    name: str
    pod_id: str = Field(foreign_key="pods.id")
    tier: str = "STANDARD"  # STANDARD, ENTERPRISE, etc.
    staffing_model: str = "SINGLE_RESOURCE"  # SINGLE_RESOURCE, MULTI_RESOURCE


class BrandProcessRule(SQLModel, table=True):
    __tablename__ = "brand_process_rules"
    id: str = Field(primary_key=True)
    brand_id: str = Field(foreign_key="brands.id")
    process_id: str = Field(foreign_key="processes.id")
    calendar_type: str = "365_DAYS"  # 365_DAYS, DAILY_EXCEPT_PH, MON_SAT_EXCEPT_PH
    min_staffing: int = 1
    day_min_staffing_overrides: Dict[str, int] = Field(default={}, sa_column=Column(JSON))


class Allocation(SQLModel, table=True):
    __tablename__ = "allocations"
    id: str = Field(primary_key=True)
    employee_id: str = Field(foreign_key="employees.id")
    brand_id: str = Field(foreign_key="brands.id")
    process_id: str = Field(foreign_key="processes.id")
    allocation_type: str = "PRIMARY"  # PRIMARY, BACKUP


class PublicHoliday(SQLModel, table=True):
    __tablename__ = "public_holidays"
    id: str = Field(primary_key=True)
    date: str  # YYYY-MM-DD
    name: str
    is_national: bool = True


class LeaveAndCompOff(SQLModel, table=True):
    __tablename__ = "leaves_and_compoffs"
    id: str = Field(primary_key=True)
    employee_id: str = Field(foreign_key="employees.id")
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD
    type: str  # PLANNED_LEAVE, COMP_OFF
    status: str = "PENDING"  # PENDING, APPROVED, REJECTED
    reason: Optional[str] = None


class Roster(SQLModel, table=True):
    __tablename__ = "rosters"
    id: str = Field(primary_key=True)  # e.g., ROST-2026-12
    month: str  # YYYY-MM
    status: str = "DRAFT"  # DRAFT, PUBLISHED
    generated_at: str  # ISO timestamp


class RosterEntry(SQLModel, table=True):
    __tablename__ = "roster_entries"
    id: Optional[int] = Field(default=None, primary_key=True)
    roster_id: str = Field(foreign_key="rosters.id")
    employee_id: str = Field(foreign_key="employees.id")
    date: str  # YYYY-MM-DD
    status: str  # WORKING, WEEKLY_OFF, PUBLIC_HOLIDAY, PLANNED_LEAVE, COMP_OFF, BACKUP_COVERAGE
    assigned_brand_id: Optional[str] = None
    assigned_process_id: Optional[str] = None
    is_manual_override: bool = False
    notes: Optional[str] = None


class RosterConflict(SQLModel, table=True):
    __tablename__ = "roster_conflicts"
    id: Optional[int] = Field(default=None, primary_key=True)
    roster_id: str = Field(foreign_key="rosters.id")
    date: str  # YYYY-MM-DD
    severity: str  # HARD, SOFT
    conflict_type: str  # UNCOVERED_BRAND_PROCESS, INSUFFICIENT_STAFFING, MULTI_BRAND_CASCADE, LEAVE_OR_OFF_VIOLATION, SHIFT_OR_OVERLOAD_CONFLICT, PREFERENCE_VIOLATED
    brand_id: Optional[str] = None
    process_id: Optional[str] = None
    employee_id: Optional[str] = None
    message: str
    suggested_resolutions: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    resolved: bool = False


class RosterNotification(SQLModel, table=True):
    __tablename__ = "roster_notifications"
    id: Optional[int] = Field(default=None, primary_key=True)
    roster_id: str
    month: str
    event_type: str  # POD_APPROVED, PUBLISHED, ENTRY_EDITED, BACKUP_ASSIGNED, LEAVE_APPROVED
    message: str
    actor_role: str = "OPS_MANAGER"
    created_at: str
    is_read: bool = False
