from fastapi import APIRouter, Depends, Query, HTTPException
from sqlmodel import Session, select, delete
from typing import Optional, List, Dict, Any
from datetime import datetime

from database import get_session
from models import (
    Pod,
    Process,
    Employee,
    Brand,
    BrandProcessRule,
    Allocation,
    PublicHoliday,
    LeaveAndCompOff,
    Roster,
    RosterEntry,
    RosterConflict,
)
from schemas import MonthlyRosterResponse, RosterEntryDTO, DailyCoverageDTO, ConflictDTO, SuggestedResolution
from engine.scheduler import generate_roster

router = APIRouter(prefix="/api/rosters", tags=["Rosters"])


@router.post("/generate", response_model=MonthlyRosterResponse)
def generate_monthly_roster(
    month: str = Query("2026-12", pattern=r"^\d{4}-\d{2}$"),
    session: Session = Depends(get_session),
):
    """
    Generates a deterministic monthly roster, evaluates coverage, detects hard/soft conflicts,
    and returns full roster entries + coverage matrix + ranked backup recommendations.
    """
    # Fetch all input entities from DB
    employees = [e.model_dump() for e in session.exec(select(Employee)).all()]
    brands = [b.model_dump() for b in session.exec(select(Brand)).all()]
    processes = [p.model_dump() for p in session.exec(select(Process)).all()]
    brand_process_rules = [r.model_dump() for r in session.exec(select(BrandProcessRule)).all()]
    allocations = [a.model_dump() for a in session.exec(select(Allocation)).all()]
    public_holidays = [ph.model_dump() for ph in session.exec(select(PublicHoliday)).all()]
    leaves_and_compoffs = [l.model_dump() for l in session.exec(select(LeaveAndCompOff)).all()]

    if not employees or not brands or not brand_process_rules:
        raise HTTPException(
            status_code=400,
            detail="Database has not been seeded with team, brand, and operating rule data.",
        )

    # Check for existing manual overrides for this month to preserve them
    existing_entries = session.exec(
        select(RosterEntry).where(RosterEntry.roster_id == f"ROST-{month}")
    ).all()
    manual_overrides = [
        e.model_dump() for e in existing_entries if e.is_manual_override
    ]

    # Run deterministic engine
    roster_result = generate_roster(
        month_str=month,
        employees=employees,
        brands=brands,
        processes=processes,
        brand_process_rules=brand_process_rules,
        allocations=allocations,
        public_holidays=public_holidays,
        leaves_and_compoffs=leaves_and_compoffs,
        manual_overrides=manual_overrides,
    )

    roster_id = f"ROST-{month}"

    # Persist in DB (clear old generated entries and conflicts for this month)
    session.exec(delete(RosterConflict).where(RosterConflict.roster_id == roster_id))
    session.exec(delete(RosterEntry).where(RosterEntry.roster_id == roster_id))
    session.exec(delete(Roster).where(Roster.id == roster_id))
    session.commit()

    # Save Roster record
    db_roster = Roster(
        id=roster_id,
        month=month,
        status="DRAFT",
        generated_at=roster_result["generated_at"],
    )
    session.add(db_roster)

    # Bulk save entries
    for entry in roster_result["entries"]:
        db_entry = RosterEntry(
            roster_id=roster_id,
            employee_id=entry["employee_id"],
            date=entry["date"],
            status=entry["status"],
            assigned_brand_id=entry.get("assigned_brand_id"),
            assigned_process_id=entry.get("assigned_process_id"),
            is_manual_override=entry.get("is_manual_override", False),
            notes=entry.get("notes"),
        )
        session.add(db_entry)

    # Bulk save conflicts
    for conf in roster_result["conflicts"]:
        db_conf = RosterConflict(
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
        session.add(db_conf)

    session.commit()

    return roster_result
