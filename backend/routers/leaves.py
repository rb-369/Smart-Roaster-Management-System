from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, delete, select

from database import get_session
from engine.scheduler import recalculate_coverage_and_validate
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


def _conflict_key(c: Dict[str, Any]) -> tuple:
    return (
        c.get("date"),
        c.get("conflict_type"),
        c.get("brand_id"),
        c.get("process_id"),
        c.get("employee_id"),
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
        employees = [e.model_dump() for e in session.exec(select(Employee)).all()]
        brands = [b.model_dump() for b in session.exec(select(Brand)).all()]
        processes = [p.model_dump() for p in session.exec(select(Process)).all()]
        brand_process_rules = [r.model_dump() for r in session.exec(select(BrandProcessRule)).all()]
        allocations = [a.model_dump() for a in session.exec(select(Allocation)).all()]
        public_holidays = [ph.model_dump() for ph in session.exec(select(PublicHoliday)).all()]
        leaves_and_compoffs = [l.model_dump() for l in session.exec(select(LeaveAndCompOff)).all()]

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

            session.commit()

            # Re-evaluate coverage & validate
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
