import csv
import io
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, delete, select

from database import get_session
from engine.scheduler import generate_roster, recalculate_coverage_and_validate
from models import (
    Allocation,
    Brand,
    BrandProcessRule,
    Employee,
    LeaveAndCompOff,
    Pod,
    Process,
    PublicHoliday,
    Roster,
    RosterConflict,
    RosterEntry,
)
from schemas import MonthlyRosterResponse

router = APIRouter(prefix="/api/rosters", tags=["Rosters"])


class RosterEntryPatchRequest(BaseModel):
    employee_id: str
    date: str
    status: str
    assigned_brand_id: Optional[str] = None
    assigned_process_id: Optional[str] = None
    notes: Optional[str] = None


class AssignBackupRequest(BaseModel):
    date: str
    brand_id: str
    process_id: str
    backup_employee_id: str


def _fetch_domain_data(session: Session) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "employees": [e.model_dump() for e in session.exec(select(Employee)).all()],
        "brands": [b.model_dump() for b in session.exec(select(Brand)).all()],
        "processes": [p.model_dump() for p in session.exec(select(Process)).all()],
        "brand_process_rules": [r.model_dump() for r in session.exec(select(BrandProcessRule)).all()],
        "allocations": [a.model_dump() for a in session.exec(select(Allocation)).all()],
        "public_holidays": [ph.model_dump() for ph in session.exec(select(PublicHoliday)).all()],
        "leaves_and_compoffs": [l.model_dump() for l in session.exec(select(LeaveAndCompOff)).all()],
    }


def _persist_conflicts(session: Session, roster_id: str, conflicts: List[Dict[str, Any]]) -> None:
    session.exec(delete(RosterConflict).where(RosterConflict.roster_id == roster_id))
    for conf in conflicts:
        session.add(
            RosterConflict(
                roster_id=roster_id,
                date=conf["date"],
                severity=conf["severity"],
                conflict_type=conf["conflict_type"],
                brand_id=conf.get("brand_id"),
                process_id=conf.get("process_id"),
                employee_id=conf.get("employee_id"),
                message=conf["message"],
                suggested_resolutions=conf.get("suggested_resolutions", []),
                resolved=conf.get("resolved", False),
            )
        )
    session.commit()


def _recalculate_from_db(session: Session, db_roster: Roster) -> Dict[str, Any]:
    domain = _fetch_domain_data(session)
    entries_db = session.exec(
        select(RosterEntry).where(RosterEntry.roster_id == db_roster.id)
    ).all()
    entry_dicts = [
        {
            "employee_id": e.employee_id,
            "date": e.date,
            "status": e.status,
            "assigned_brand_id": e.assigned_brand_id,
            "assigned_process_id": e.assigned_process_id,
            "is_manual_override": e.is_manual_override,
            "notes": e.notes,
        }
        for e in entries_db
    ]
    result = recalculate_coverage_and_validate(
        month_str=db_roster.month,
        entries=entry_dicts,
        employees=domain["employees"],
        brands=domain["brands"],
        processes=domain["processes"],
        brand_process_rules=domain["brand_process_rules"],
        allocations=domain["allocations"],
        public_holidays=domain["public_holidays"],
        leaves_and_compoffs=domain["leaves_and_compoffs"],
        roster_status=db_roster.status,
        generated_at=db_roster.generated_at,
    )
    result["_domain"] = domain
    return result


@router.post("/generate", response_model=MonthlyRosterResponse)
def generate_monthly_roster(
    month: str = Query("2026-12", pattern=r"^\d{4}-\d{2}$"),
    session: Session = Depends(get_session),
):
    """
    Generates a deterministic monthly roster, evaluates coverage, detects hard/soft conflicts,
    and returns full roster entries + coverage matrix + ranked backup recommendations.
    """
    domain = _fetch_domain_data(session)

    if not domain["employees"] or not domain["brands"] or not domain["brand_process_rules"]:
        raise HTTPException(
            status_code=400,
            detail="Database has not been seeded with team, brand, and operating rule data.",
        )

    roster_id = f"ROST-{month}"
    existing_entries = session.exec(
        select(RosterEntry).where(RosterEntry.roster_id == roster_id)
    ).all()
    manual_overrides = [e.model_dump() for e in existing_entries if e.is_manual_override]

    roster_result = generate_roster(
        month_str=month,
        employees=domain["employees"],
        brands=domain["brands"],
        processes=domain["processes"],
        brand_process_rules=domain["brand_process_rules"],
        allocations=domain["allocations"],
        public_holidays=domain["public_holidays"],
        leaves_and_compoffs=domain["leaves_and_compoffs"],
        manual_overrides=manual_overrides,
    )

    session.exec(delete(RosterConflict).where(RosterConflict.roster_id == roster_id))
    session.exec(delete(RosterEntry).where(RosterEntry.roster_id == roster_id))
    session.exec(delete(Roster).where(Roster.id == roster_id))
    session.commit()

    db_roster = Roster(
        id=roster_id,
        month=month,
        status="DRAFT",
        generated_at=roster_result["generated_at"],
    )
    session.add(db_roster)

    for entry in roster_result["entries"]:
        session.add(
            RosterEntry(
                roster_id=roster_id,
                employee_id=entry["employee_id"],
                date=entry["date"],
                status=entry["status"],
                assigned_brand_id=entry.get("assigned_brand_id"),
                assigned_process_id=entry.get("assigned_process_id"),
                is_manual_override=entry.get("is_manual_override", False),
                notes=entry.get("notes"),
            )
        )

    session.commit()
    _persist_conflicts(session, roster_id, roster_result["conflicts"])

    return roster_result


@router.get("/{month}/export.csv")
def export_roster_csv(
    month: str = Path(..., pattern=r"^\d{4}-\d{2}$"),
    session: Session = Depends(get_session),
):
    """Stream the monthly roster as a downloadable CSV file."""
    roster_id = f"ROST-{month}"
    db_roster = session.get(Roster, roster_id)
    if not db_roster:
        raise HTTPException(status_code=404, detail=f"Roster for '{month}' not found")

    entries = session.exec(
        select(RosterEntry).where(RosterEntry.roster_id == roster_id)
    ).all()
    employees = {e.id: e for e in session.exec(select(Employee)).all()}
    pods = {p.id: p for p in session.exec(select(Pod)).all()}

    sorted_entries = sorted(entries, key=lambda e: (e.employee_id, e.date))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Employee ID",
        "Employee Name",
        "Pod",
        "Role",
        "Date",
        "Status",
        "Assigned Brand",
        "Assigned Process",
        "Manual Override",
        "Notes",
    ])

    for entry in sorted_entries:
        emp = employees.get(entry.employee_id)
        pod_name = pods[emp.pod_id].name if emp and emp.pod_id in pods else (emp.pod_id if emp else "")
        writer.writerow([
            entry.employee_id,
            emp.name if emp else "",
            pod_name,
            emp.role if emp else "",
            entry.date,
            entry.status,
            entry.assigned_brand_id or "",
            entry.assigned_process_id or "",
            "Yes" if entry.is_manual_override else "No",
            entry.notes or "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="roster-{month}.csv"'},
    )


@router.get("/{month}", response_model=MonthlyRosterResponse)
def get_monthly_roster(
    month: str = Path(..., pattern=r"^\d{4}-\d{2}$"),
    view: str = Query("company", pattern=r"^(company|pod|brand|process|employee)$"),
    filter_id: Optional[str] = Query(None),
    session: Session = Depends(get_session),
):
    """
    Fetch an existing monthly roster with fresh coverage_matrix, conflicts, and KPIs,
    optionally filtered by stakeholder view (company, pod, brand, process, employee).
    """
    roster_id = f"ROST-{month}"
    db_roster = session.get(Roster, roster_id)
    if not db_roster:
        raise HTTPException(status_code=404, detail=f"Roster for '{month}' not found")

    result = _recalculate_from_db(session, db_roster)
    domain = result.pop("_domain")

    if view != "company" and filter_id:
        employees = domain["employees"]
        brands = domain["brands"]
        allocations = domain["allocations"]
        entries = result["entries"]
        coverage_matrix = result["coverage_matrix"]
        conflicts = result["conflicts"]

        if view == "pod":
            pod_emp_ids = {e["id"] for e in employees if e["pod_id"] == filter_id}
            pod_brand_ids = {b["id"] for b in brands if b["pod_id"] == filter_id}
            result["entries"] = [e for e in entries if e["employee_id"] in pod_emp_ids]
            result["coverage_matrix"] = [c for c in coverage_matrix if c["brand_id"] in pod_brand_ids]
            result["conflicts"] = [
                c for c in conflicts
                if c.get("brand_id") in pod_brand_ids or c.get("employee_id") in pod_emp_ids
            ]
        elif view == "brand":
            brand_emp_ids = {
                a["employee_id"] for a in allocations if a["brand_id"] == filter_id
            } | {
                e["employee_id"] for e in entries if e.get("assigned_brand_id") == filter_id
            }
            result["entries"] = [e for e in entries if e["employee_id"] in brand_emp_ids]
            result["coverage_matrix"] = [c for c in coverage_matrix if c["brand_id"] == filter_id]
            result["conflicts"] = [c for c in conflicts if c.get("brand_id") == filter_id]
        elif view == "process":
            proc_emp_ids = {
                a["employee_id"] for a in allocations if a["process_id"] == filter_id
            } | {
                e["employee_id"] for e in entries if e.get("assigned_process_id") == filter_id
            }
            result["entries"] = [e for e in entries if e["employee_id"] in proc_emp_ids]
            result["coverage_matrix"] = [c for c in coverage_matrix if c["process_id"] == filter_id]
            result["conflicts"] = [c for c in conflicts if c.get("process_id") == filter_id]
        elif view == "employee":
            emp_bps = {
                (a["brand_id"], a["process_id"])
                for a in allocations
                if a["employee_id"] == filter_id
            } | {
                (e.get("assigned_brand_id"), e.get("assigned_process_id"))
                for e in entries
                if e["employee_id"] == filter_id
                and e.get("assigned_brand_id")
                and e.get("assigned_process_id")
            }
            result["entries"] = [e for e in entries if e["employee_id"] == filter_id]
            result["coverage_matrix"] = [
                c for c in coverage_matrix if (c["brand_id"], c["process_id"]) in emp_bps
            ]
            result["conflicts"] = [
                c for c in conflicts
                if c.get("employee_id") == filter_id
                or (c.get("brand_id"), c.get("process_id")) in emp_bps
            ]

    return result


@router.patch("/{month}/entry", response_model=MonthlyRosterResponse)
def patch_roster_entry(
    payload: RosterEntryPatchRequest,
    month: str = Path(..., pattern=r"^\d{4}-\d{2}$"),
    session: Session = Depends(get_session),
):
    """
    Manually edit a single employee's roster entry for a date, mark as manual override,
    and immediately re-validate coverage and conflicts.
    """
    roster_id = f"ROST-{month}"
    db_roster = session.get(Roster, roster_id)
    if not db_roster:
        raise HTTPException(status_code=404, detail=f"Roster for '{month}' not found")

    db_entry = session.exec(
        select(RosterEntry).where(
            RosterEntry.roster_id == roster_id,
            RosterEntry.employee_id == payload.employee_id,
            RosterEntry.date == payload.date,
        )
    ).first()
    if not db_entry:
        raise HTTPException(
            status_code=404,
            detail=f"RosterEntry for employee '{payload.employee_id}' on '{payload.date}' not found",
        )

    db_entry.status = payload.status
    db_entry.assigned_brand_id = payload.assigned_brand_id
    db_entry.assigned_process_id = payload.assigned_process_id
    db_entry.is_manual_override = True
    if payload.notes is not None:
        db_entry.notes = payload.notes
    session.add(db_entry)
    session.commit()

    result = _recalculate_from_db(session, db_roster)
    result.pop("_domain", None)
    _persist_conflicts(session, roster_id, result["conflicts"])
    return result


@router.post("/{month}/assign-backup", response_model=MonthlyRosterResponse)
def assign_backup(
    payload: AssignBackupRequest,
    month: str = Path(..., pattern=r"^\d{4}-\d{2}$"),
    session: Session = Depends(get_session),
):
    """
    Assign a backup employee to cover a brand-process gap on a specific date,
    and immediately re-validate coverage and conflicts.
    """
    roster_id = f"ROST-{month}"
    db_roster = session.get(Roster, roster_id)
    if not db_roster:
        raise HTTPException(status_code=404, detail=f"Roster for '{month}' not found")

    db_entry = session.exec(
        select(RosterEntry).where(
            RosterEntry.roster_id == roster_id,
            RosterEntry.employee_id == payload.backup_employee_id,
            RosterEntry.date == payload.date,
        )
    ).first()
    if not db_entry:
        raise HTTPException(
            status_code=404,
            detail=f"RosterEntry for backup employee '{payload.backup_employee_id}' on '{payload.date}' not found",
        )

    db_entry.status = "BACKUP_COVERAGE"
    db_entry.assigned_brand_id = payload.brand_id
    db_entry.assigned_process_id = payload.process_id
    db_entry.is_manual_override = True
    db_entry.notes = f"Backup for {payload.brand_id} ({payload.process_id})"
    session.add(db_entry)
    session.commit()

    result = _recalculate_from_db(session, db_roster)
    result.pop("_domain", None)
    _persist_conflicts(session, roster_id, result["conflicts"])
    return result
