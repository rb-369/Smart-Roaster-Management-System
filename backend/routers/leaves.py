from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, delete, select

from database import get_session
from engine.scheduler import (
    _conflict_key,
    preview_leave_impact,
    recalculate_coverage_and_validate,
)
from models import (
    Allocation,
    Brand,
    BrandProcessRule,
    Employee,
    LeaveAndCompOff,
    Process,
    PublicHoliday,
    Roster,
    RosterConflict,
    RosterEntry,
    RosterNotification,
)
from routers._crud import register_crud_routes
from schemas import LeaveImpactPreviewResponse, LeavePreviewRequest

router = APIRouter(prefix="/api", tags=["Leaves & Holidays"])

register_crud_routes(router, "/holidays", PublicHoliday, prefix="PH-", pad=2)
register_crud_routes(router, "/leaves", LeaveAndCompOff, prefix="LV-", pad=2)


def _months_in_range(start_date: str, end_date: str) -> List[str]:
    """Return sorted distinct YYYY-MM strings spanned by start_date..end_date."""
    start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_d = datetime.strptime(end_date, "%Y-%m-%d").date()
    months: List[str] = []
    cur = start_d
    while cur <= end_d:
        m_str = cur.strftime("%Y-%m")
        if m_str not in months:
            months.append(m_str)
        cur += timedelta(days=1)
    return months


def _fetch_domain_data(session: Session) -> Dict[str, List[Dict[str, Any]]]:
    """Load canonical domain tables as plain dicts for pure engine calls."""
    return {
        "employees": [e.model_dump() for e in session.exec(select(Employee)).all()],
        "brands": [b.model_dump() for b in session.exec(select(Brand)).all()],
        "processes": [p.model_dump() for p in session.exec(select(Process)).all()],
        "brand_process_rules": [r.model_dump() for r in session.exec(select(BrandProcessRule)).all()],
        "allocations": [a.model_dump() for a in session.exec(select(Allocation)).all()],
        "public_holidays": [ph.model_dump() for ph in session.exec(select(PublicHoliday)).all()],
        "leaves_and_compoffs": [l.model_dump() for l in session.exec(select(LeaveAndCompOff)).all()],
    }


def _roster_entry_to_dict(entry: RosterEntry) -> Dict[str, Any]:
    return {
        "employee_id": entry.employee_id,
        "date": entry.date,
        "status": entry.status,
        "assigned_brand_id": entry.assigned_brand_id,
        "assigned_process_id": entry.assigned_process_id,
        "is_manual_override": entry.is_manual_override,
        "notes": entry.notes,
    }


def _run_leave_preview(
    session: Session,
    month: str,
    employee_id: str,
    start_date: str,
    end_date: str,
    leave_type: str,
    leave_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a pure dry-run leave impact preview against the stored roster without DB writes."""
    roster_id = f"ROST-{month}"
    db_roster = session.get(Roster, roster_id)
    if not db_roster:
        raise HTTPException(
            status_code=404,
            detail=f"Roster for '{month}' not found. Generate the roster first.",
        )

    emp = session.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail=f"Employee '{employee_id}' not found")

    domain = _fetch_domain_data(session)
    entries_db = session.exec(
        select(RosterEntry).where(RosterEntry.roster_id == roster_id)
    ).all()
    entry_dicts = [_roster_entry_to_dict(e) for e in entries_db]

    impact = preview_leave_impact(
        month_str=month,
        entries=entry_dicts,
        employee_id=employee_id,
        start_date=start_date,
        end_date=end_date,
        leave_type=leave_type,
        employees=domain["employees"],
        brands=domain["brands"],
        processes=domain["processes"],
        brand_process_rules=domain["brand_process_rules"],
        allocations=domain["allocations"],
        public_holidays=domain["public_holidays"],
        leaves_and_compoffs=domain["leaves_and_compoffs"],
    )
    return {
        "month": month,
        "leave_id": leave_id,
        "employee_id": employee_id,
        "employee_name": emp.name,
        "start_date": start_date,
        "end_date": end_date,
        "type": leave_type,
        **impact,
    }


@router.post("/leaves/preview-impact", response_model=LeaveImpactPreviewResponse)
def preview_adhoc_leave_impact(
    payload: LeavePreviewRequest,
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    session: Session = Depends(get_session),
):
    """Preview impact of a prospective leave request without creating or mutating DB rows."""
    try:
        start_d = datetime.strptime(payload.start_date, "%Y-%m-%d").date()
        end_d = datetime.strptime(payload.end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="start_date and end_date must be valid YYYY-MM-DD dates.",
        )
    if end_d < start_d:
        raise HTTPException(
            status_code=422,
            detail="end_date must be on or after start_date.",
        )
    if payload.type not in ("PLANNED_LEAVE", "COMP_OFF"):
        raise HTTPException(
            status_code=422,
            detail="type must be 'PLANNED_LEAVE' or 'COMP_OFF'.",
        )

    target_month = month or payload.start_date[:7]
    return _run_leave_preview(
        session=session,
        month=target_month,
        employee_id=payload.employee_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        leave_type=payload.type,
    )


@router.post("/leaves/{leave_id}/preview-impact", response_model=LeaveImpactPreviewResponse)
def preview_existing_leave_impact(
    leave_id: str,
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    session: Session = Depends(get_session),
):
    """Preview impact of approving an existing leave/comp-off without mutating DB state."""
    leave = session.get(LeaveAndCompOff, leave_id)
    if not leave:
        raise HTTPException(status_code=404, detail=f"Leave '{leave_id}' not found")

    target_month = month or leave.start_date[:7]
    return _run_leave_preview(
        session=session,
        month=target_month,
        employee_id=leave.employee_id,
        start_date=leave.start_date,
        end_date=leave.end_date,
        leave_type=leave.type,
        leave_id=leave.id,
    )


@router.post("/leaves/{leave_id}/approve")
def approve_leave(leave_id: str, session: Session = Depends(get_session)):
    """
    Approve a leave/comp-off request. If a roster exists for the spanned month(s),
    updates affected RosterEntry rows, re-runs coverage & validation, persists
    updated conflicts, and returns leave + impact + updated roster.
    """
    leave = session.get(LeaveAndCompOff, leave_id)
    if not leave:
        raise HTTPException(status_code=404, detail=f"Leave '{leave_id}' not found")

    leave.status = "APPROVED"
    session.add(leave)
    session.commit()
    session.refresh(leave)
    leave_dict = leave.model_dump()

    months = _months_in_range(leave.start_date, leave.end_date)
    primary_roster_result: Optional[Dict[str, Any]] = None
    hard_conflicts_before = 0
    hard_conflicts_after = 0
    new_conflicts: List[Dict[str, Any]] = []
    affected_brands_set = set()

    # Fetch shared entity data once if any roster exists
    existing_rosters = [
        r for r in (session.get(Roster, f"ROST-{m}") for m in months) if r is not None
    ]

    if existing_rosters:
        domain = _fetch_domain_data(session)
        employees = domain["employees"]
        brands = domain["brands"]
        processes = domain["processes"]
        brand_process_rules = domain["brand_process_rules"]
        allocations = domain["allocations"]
        public_holidays = domain["public_holidays"]
        leaves_and_compoffs = domain["leaves_and_compoffs"]

        for db_roster in existing_rosters:
            roster_id = db_roster.id
            month_str = db_roster.month

            prev_conflicts = session.exec(
                select(RosterConflict).where(RosterConflict.roster_id == roster_id)
            ).all()
            prev_hard_keys = {
                _conflict_key(c.model_dump())
                for c in prev_conflicts
                if c.severity == "HARD"
            }
            hard_conflicts_before += len(prev_hard_keys)

            # Update affected RosterEntry rows for this employee in start_date..end_date
            entries_db = session.exec(
                select(RosterEntry).where(RosterEntry.roster_id == roster_id)
            ).all()

            for entry in entries_db:
                if (
                    entry.employee_id == leave.employee_id
                    and leave.start_date <= entry.date <= leave.end_date
                ):
                    entry.status = leave.type
                    entry.assigned_brand_id = None
                    entry.assigned_process_id = None
                    entry.is_manual_override = False
                    entry.notes = f"Approved {leave.type}" + (
                        f": {leave.reason}" if leave.reason else ""
                    )
                    session.add(entry)

            entry_dicts = [_roster_entry_to_dict(e) for e in entries_db]
            session.commit()

            # Re-evaluate coverage & validate
            updated_roster = recalculate_coverage_and_validate(
                month_str=month_str,
                entries=entry_dicts,
                employees=employees,
                brands=brands,
                processes=processes,
                brand_process_rules=brand_process_rules,
                allocations=allocations,
                public_holidays=public_holidays,
                leaves_and_compoffs=leaves_and_compoffs,
                roster_status=db_roster.status,
                generated_at=db_roster.generated_at,
            )

            # Persist updated RosterConflict rows
            session.exec(delete(RosterConflict).where(RosterConflict.roster_id == roster_id))
            for conf in updated_roster["conflicts"]:
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

            hard_conflicts_after += updated_roster["kpis"]["hard_conflicts_count"]
            for conf in updated_roster["conflicts"]:
                if conf["severity"] == "HARD" and _conflict_key(conf) not in prev_hard_keys:
                    new_conflicts.append(conf)
                    if conf.get("brand_id"):
                        affected_brands_set.add(conf["brand_id"])

            if primary_roster_result is None:
                primary_roster_result = updated_roster

            if db_roster.status == "PUBLISHED":
                emp_obj = next((e for e in employees if e["id"] == leave.employee_id), None)
                emp_name = emp_obj["name"] if emp_obj else leave.employee_id
                session.add(
                    RosterNotification(
                        roster_id=roster_id,
                        month=month_str,
                        event_type="LEAVE_APPROVED",
                        message=(
                            f"Approved {leave.type} for {emp_name} ({leave.start_date} to {leave.end_date}) "
                            f"on published roster {month_str}."
                        ),
                        actor_role="OPS_MANAGER",
                        created_at=datetime.now(timezone.utc).isoformat(),
                        is_read=False,
                    )
                )
                session.commit()

    return {
        "leave": leave_dict,
        "impact": {
            "hard_conflicts_before": hard_conflicts_before,
            "hard_conflicts_after": hard_conflicts_after,
            "new_conflicts": new_conflicts,
            "affected_brands": sorted(affected_brands_set),
        },
        "roster": primary_roster_result,
    }


@router.post("/leaves/{leave_id}/reject")
def reject_leave(leave_id: str, session: Session = Depends(get_session)):
    """Reject a leave/comp-off request."""
    leave = session.get(LeaveAndCompOff, leave_id)
    if not leave:
        raise HTTPException(status_code=404, detail=f"Leave '{leave_id}' not found")
    leave.status = "REJECTED"
    session.add(leave)
    session.commit()
    session.refresh(leave)
    return leave.model_dump()
