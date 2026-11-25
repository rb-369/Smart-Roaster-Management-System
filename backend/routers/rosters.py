import csv
import io
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
import openpyxl
from openpyxl.styles import Font, PatternFill
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from fastapi.responses import JSONResponse, StreamingResponse
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
    RosterNotification,
)
from schemas import MonthlyRosterResponse

router = APIRouter(prefix="/api/rosters", tags=["Rosters"])
notifications_router = APIRouter(prefix="/api", tags=["Notifications"])


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


class PodApproveRequest(BaseModel):
    actor_role: str = "POD_LEAD"


class PublishRosterRequest(BaseModel):
    force: bool = False
    actor_role: str = "OPS_MANAGER"


class ExplainConflictRequest(BaseModel):
    date: str
    conflict_type: str
    severity: str
    brand_name: Optional[str] = None
    process_name: Optional[str] = None
    employee_name: Optional[str] = None
    message: str
    suggested_resolutions: List[Dict[str, Any]] = []


STATUS_CODE_MAP = {
    "WORKING": "W",
    "WEEKLY_OFF": "WO",
    "PUBLIC_HOLIDAY": "PH",
    "PLANNED_LEAVE": "LV",
    "COMP_OFF": "CO",
    "BACKUP_COVERAGE": "BK",
}


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


def _create_notification(
    session: Session,
    roster_id: str,
    month: str,
    event_type: str,
    message: str,
    actor_role: str = "OPS_MANAGER",
) -> RosterNotification:
    notif = RosterNotification(
        roster_id=roster_id,
        month=month,
        event_type=event_type,
        message=message,
        actor_role=actor_role,
        created_at=datetime.now(timezone.utc).isoformat(),
        is_read=False,
    )
    session.add(notif)
    session.commit()
    session.refresh(notif)
    return notif


def _persist_generated_roster(
    session: Session,
    month: str,
    roster_result: Dict[str, Any],
) -> None:
    roster_id = f"ROST-{month}"
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


def _get_notifications_impl(session: Session, month: Optional[str] = None) -> List[Dict[str, Any]]:
    stmt = select(RosterNotification)
    if month:
        stmt = stmt.where(RosterNotification.month == month)
    stmt = stmt.order_by(RosterNotification.id.desc())
    return [n.model_dump() for n in session.exec(stmt).all()]


def _mark_notifications_read_impl(session: Session, month: Optional[str] = None) -> Dict[str, Any]:
    stmt = select(RosterNotification).where(RosterNotification.is_read == False)  # noqa: E712
    if month:
        stmt = stmt.where(RosterNotification.month == month)
    items = session.exec(stmt).all()
    for item in items:
        item.is_read = True
        session.add(item)
    session.commit()
    return {"status": "ok", "updated": len(items)}


@notifications_router.get("/notifications")
def list_notifications(
    month: Optional[str] = Query(None),
    session: Session = Depends(get_session),
):
    """List roster notifications ordered newest first."""
    return _get_notifications_impl(session, month)


@notifications_router.post("/notifications/mark-read")
def mark_notifications_read(
    month: Optional[str] = Query(None),
    session: Session = Depends(get_session),
):
    """Mark all (or month-scoped) notifications as read."""
    return _mark_notifications_read_impl(session, month)


@router.get("/notifications")
def list_roster_notifications(
    month: Optional[str] = Query(None),
    session: Session = Depends(get_session),
):
    """Alias for listing roster notifications ordered newest first."""
    return _get_notifications_impl(session, month)


@router.post("/notifications/mark-read")
def mark_roster_notifications_read(
    month: Optional[str] = Query(None),
    session: Session = Depends(get_session),
):
    """Alias for marking notifications as read."""
    return _mark_notifications_read_impl(session, month)


@router.post("/generate", response_model=MonthlyRosterResponse)
def generate_monthly_roster(
    month: str = Query("2026-12", pattern=r"^\d{4}-\d{2}$"),
    strategy: str = Query("BALANCED", pattern=r"^(COVERAGE_FIRST|PREFERENCE_FIRST|BALANCED)$"),
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
        strategy=strategy,
    )

    _persist_generated_roster(session, month, roster_result)
    return roster_result


@router.post("/{month}/compare-plans")
def compare_plans(
    month: str = Path(..., pattern=r"^\d{4}-\d{2}$"),
    session: Session = Depends(get_session),
):
    """Run in-memory roster generation for all 3 strategies and return KPI comparison."""
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

    plan_specs = [
        (
            "COVERAGE_FIRST",
            "Coverage First",
            "Staggers all multi-resource peers aggressively and shifts off peak days to maximize client coverage.",
        ),
        (
            "BALANCED",
            "Balanced",
            "Standard rotational staggering with weekly Sunday fairness rotation while respecting fixed offs.",
        ),
        (
            "PREFERENCE_FIRST",
            "Preference First",
            "Strictly honors every employee's preferred weekly off without staggering, surfacing all coverage gaps.",
        ),
    ]

    plans = []
    for strategy_key, label, desc in plan_specs:
        res = generate_roster(
            month_str=month,
            employees=domain["employees"],
            brands=domain["brands"],
            processes=domain["processes"],
            brand_process_rules=domain["brand_process_rules"],
            allocations=domain["allocations"],
            public_holidays=domain["public_holidays"],
            leaves_and_compoffs=domain["leaves_and_compoffs"],
            manual_overrides=manual_overrides,
            strategy=strategy_key,
        )
        plans.append({
            "strategy": strategy_key,
            "label": label,
            "description": desc,
            "kpis": res["kpis"],
        })

    return {"month": month, "plans": plans}


@router.post("/{month}/apply-plan", response_model=MonthlyRosterResponse)
def apply_plan(
    month: str = Path(..., pattern=r"^\d{4}-\d{2}$"),
    strategy: str = Query("BALANCED", pattern=r"^(COVERAGE_FIRST|PREFERENCE_FIRST|BALANCED)$"),
    session: Session = Depends(get_session),
):
    """Generate and persist the chosen strategy's roster to the database."""
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
        strategy=strategy,
    )
    _persist_generated_roster(session, month, roster_result)
    return roster_result


@router.post("/{month}/approve-pod", response_model=MonthlyRosterResponse)
def approve_pod_roster(
    month: str = Path(..., pattern=r"^\d{4}-\d{2}$"),
    payload: PodApproveRequest = Body(default_factory=PodApproveRequest),
    session: Session = Depends(get_session),
):
    """Transition a DRAFT roster to POD_APPROVED and record a notification."""
    roster_id = f"ROST-{month}"
    db_roster = session.get(Roster, roster_id)
    if not db_roster:
        raise HTTPException(status_code=404, detail=f"Roster for '{month}' not found")

    if db_roster.status == "DRAFT":
        db_roster.status = "POD_APPROVED"
        session.add(db_roster)
        session.commit()
        session.refresh(db_roster)

    _create_notification(
        session=session,
        roster_id=roster_id,
        month=month,
        event_type="POD_APPROVED",
        message=f"Pod Lead ({payload.actor_role}) approved roster {month} for Ops review.",
        actor_role=payload.actor_role,
    )

    result = _recalculate_from_db(session, db_roster)
    result.pop("_domain", None)
    return result


@router.post("/{month}/publish", response_model=MonthlyRosterResponse)
def publish_roster(
    month: str = Path(..., pattern=r"^\d{4}-\d{2}$"),
    payload: PublishRosterRequest = Body(default_factory=PublishRosterRequest),
    session: Session = Depends(get_session),
):
    """Publish a roster; blocks with HTTP 409 if hard conflicts exist unless force=True."""
    roster_id = f"ROST-{month}"
    db_roster = session.get(Roster, roster_id)
    if not db_roster:
        raise HTTPException(status_code=404, detail=f"Roster for '{month}' not found")

    result = _recalculate_from_db(session, db_roster)
    result.pop("_domain", None)
    hard_count = result["kpis"]["hard_conflicts_count"]

    if hard_count > 0 and not payload.force:
        return JSONResponse(
            status_code=409,
            content={
                "detail": "Cannot publish with active hard conflicts unless forced.",
                "hard_conflicts_count": hard_count,
                "requires_force": True,
            },
        )

    db_roster.status = "PUBLISHED"
    session.add(db_roster)
    session.commit()
    session.refresh(db_roster)

    _create_notification(
        session=session,
        roster_id=roster_id,
        month=month,
        event_type="PUBLISHED",
        message=(
            f"Roster {month} published by {payload.actor_role}"
            + (f" (forced with {hard_count} hard conflicts)." if hard_count > 0 else ".")
        ),
        actor_role=payload.actor_role,
    )

    result["status"] = "PUBLISHED"
    return result


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


@router.get("/{month}/export.xlsx")
def export_roster_xlsx(
    month: str = Path(..., pattern=r"^\d{4}-\d{2}$"),
    session: Session = Depends(get_session),
):
    """Stream the monthly roster as a 3-sheet Excel (.xlsx) workbook."""
    roster_id = f"ROST-{month}"
    db_roster = session.get(Roster, roster_id)
    if not db_roster:
        raise HTTPException(status_code=404, detail=f"Roster for '{month}' not found")

    result = _recalculate_from_db(session, db_roster)
    domain = result.pop("_domain")
    employees = sorted(domain["employees"], key=lambda e: e["id"])
    pods = {p.id: p.name for p in session.exec(select(Pod)).all()}

    entries_by_emp_date: Dict[tuple, Dict[str, Any]] = {
        (e["employee_id"], e["date"]): e for e in result["entries"]
    }
    dates = sorted({e["date"] for e in result["entries"]})

    wb = openpyxl.Workbook()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")

    # Sheet 1: Roster Matrix
    ws_matrix = wb.active
    ws_matrix.title = "Roster Matrix"
    matrix_headers = ["Employee ID", "Employee Name", "Pod", "Role"] + dates
    ws_matrix.append(matrix_headers)
    for cell in ws_matrix[1]:
        cell.font = header_font
        cell.fill = header_fill

    for emp in employees:
        pod_name = pods.get(emp["pod_id"], emp["pod_id"])
        row = [emp["id"], emp["name"], pod_name, emp["role"]]
        for d in dates:
            entry = entries_by_emp_date.get((emp["id"], d))
            code = STATUS_CODE_MAP.get(entry["status"], entry["status"]) if entry else ""
            row.append(code)
        ws_matrix.append(row)

    # Sheet 2: Coverage Summary
    ws_cov = wb.create_sheet(title="Coverage Summary")
    cov_headers = [
        "Date",
        "Brand ID",
        "Brand Name",
        "Process",
        "Calendar Type",
        "Operating",
        "Required Staffing",
        "Working Count",
        "Status",
        "Assigned Employees",
        "Backup Employees",
    ]
    ws_cov.append(cov_headers)
    for cell in ws_cov[1]:
        cell.font = header_font
        cell.fill = header_fill

    for cov in result["coverage_matrix"]:
        ws_cov.append([
            cov["date"],
            cov["brand_id"],
            cov["brand_name"],
            cov["process_code"],
            cov["calendar_type"],
            "Yes" if cov["is_operating"] else "No",
            cov["required_staffing"],
            cov["working_count"],
            cov["status"],
            ", ".join(cov.get("assigned_employee_ids", [])),
            ", ".join(cov.get("backup_employee_ids", [])),
        ])

    # Sheet 3: Conflicts
    ws_conf = wb.create_sheet(title="Conflicts")
    conf_headers = [
        "Date",
        "Severity",
        "Conflict Type",
        "Brand",
        "Process",
        "Employee",
        "Message",
        "Top Suggested Resolution",
    ]
    ws_conf.append(conf_headers)
    for cell in ws_conf[1]:
        cell.font = header_font
        cell.fill = header_fill

    for conf in result["conflicts"]:
        resolutions = conf.get("suggested_resolutions", [])
        top_res = (
            f"{resolutions[0]['name']} ({resolutions[0]['employee_id']}, score {resolutions[0]['score']})"
            if resolutions
            else ""
        )
        ws_conf.append([
            conf["date"],
            conf["severity"],
            conf["conflict_type"],
            conf.get("brand_name") or conf.get("brand_id") or "",
            conf.get("process_name") or conf.get("process_id") or "",
            conf.get("employee_name") or conf.get("employee_id") or "",
            conf["message"],
            top_res,
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="roster-{month}.xlsx"'},
    )


def _parse_ai_json_response(text: str) -> Optional[Dict[str, Any]]:
    """Attempt to extract explanation & action_steps from LLM output."""
    cleaned = text.strip()
    if "```" in cleaned:
        parts = cleaned.split("```")
        for part in parts:
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{"):
                cleaned = candidate
                break
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and isinstance(data.get("explanation"), str) and isinstance(data.get("action_steps"), list):
            steps = [str(s) for s in data["action_steps"] if str(s).strip()][:3]
            if steps:
                return {"explanation": data["explanation"].strip(), "action_steps": steps}
    except Exception:
        pass
    return None


def _deterministic_explain(payload: ExplainConflictRequest) -> Dict[str, Any]:
    """Deterministic fallback explanation and action steps."""
    brand_label = payload.brand_name or "the affected brand"
    proc_label = payload.process_name or "operations"
    emp_label = payload.employee_name or "the assigned specialist"

    if payload.conflict_type in ("UNCOVERED_BRAND_PROCESS", "INSUFFICIENT_STAFFING"):
        explanation = (
            f"On {payload.date}, {brand_label} ({proc_label}) has a {payload.severity.lower()} staffing gap. "
            f"{payload.message}"
        )
    elif payload.conflict_type == "MULTI_BRAND_CASCADE":
        explanation = (
            f"On {payload.date}, {emp_label}'s absence creates a cascading coverage gap across multiple brands. "
            f"{payload.message}"
        )
    elif payload.conflict_type == "PREFERENCE_VIOLATED":
        explanation = (
            f"On {payload.date}, a soft preference override occurred for {emp_label} on {brand_label} "
            f"to preserve client coverage."
        )
    else:
        explanation = f"Conflict on {payload.date} ({payload.conflict_type}): {payload.message}"

    action_steps: List[str] = []
    if payload.suggested_resolutions:
        top = payload.suggested_resolutions[0]
        top_name = top.get("name", top.get("employee_id", "top backup"))
        top_score = top.get("score", "")
        top_reason = top.get("reason", "available backup")
        action_steps.append(
            f"Assign top-ranked backup {top_name} (score {top_score}: {top_reason}) for {payload.date}."
        )
        if len(payload.suggested_resolutions) > 1:
            alt = payload.suggested_resolutions[1]
            action_steps.append(
                f"Keep {alt.get('name', alt.get('employee_id', 'secondary backup'))} on standby as secondary coverage."
            )
    else:
        action_steps.append(
            f"Review pod capacity for {brand_label} on {payload.date} and reassign an available floater or Pod Lead."
        )

    action_steps.append(
        f"Verify {brand_label} ({proc_label}) coverage status updates to COVERED/BACKUP_COVERED after adjustment."
    )
    return {
        "explanation": explanation,
        "action_steps": action_steps[:3],
        "provider": "Deterministic Smart Engine",
    }


@router.post("/{month}/explain-conflict")
def explain_conflict(
    payload: ExplainConflictRequest,
    month: str = Path(..., pattern=r"^\d{4}-\d{2}$"),
):
    """
    Explain a roster conflict and suggest concrete action steps using AI providers
    (OpenRouter -> Gemini -> NVIDIA NIM) with a deterministic fallback.
    """
    prompt = (
        f"You are an operations workforce planning assistant for roster month {month}.\n"
        f"Conflict: {payload.severity} {payload.conflict_type} on {payload.date}.\n"
        f"Brand: {payload.brand_name or 'N/A'}, Process: {payload.process_name or 'N/A'}, "
        f"Employee: {payload.employee_name or 'N/A'}.\n"
        f"Details: {payload.message}\n"
        f"Suggested backups: {json.dumps(payload.suggested_resolutions[:3])}\n\n"
        'Respond ONLY with valid JSON: {"explanation": "<concise 1-2 sentence explanation>", '
        '"action_steps": ["<step 1>", "<step 2>", "<step 3>"]}.'
    )

    # 1. OpenRouter
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if openrouter_key:
        for model_name in ("nvidia/nemotron-3-ultra-550b-a55b:free", "openrouter/free"):
            try:
                with httpx.Client(timeout=8.0) as client:
                    resp = client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {openrouter_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model_name,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.2,
                        },
                    )
                    if resp.status_code == 200:
                        content = resp.json()["choices"][0]["message"]["content"]
                        parsed = _parse_ai_json_response(content)
                        if parsed:
                            parsed["provider"] = f"OpenRouter ({model_name})"
                            return parsed
            except Exception:
                continue

    # 2. Gemini
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gemini_key:
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}",
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                )
                if resp.status_code == 200:
                    content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    parsed = _parse_ai_json_response(content)
                    if parsed:
                        parsed["provider"] = "Gemini (gemini-2.0-flash)"
                        return parsed
        except Exception:
            pass

    # 3. NVIDIA NIM
    nvidia_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if nvidia_key:
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(
                    "https://integrate.api.nvidia.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {nvidia_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "nvidia/llama-3.1-nemotron-70b-instruct",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                    },
                )
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    parsed = _parse_ai_json_response(content)
                    if parsed:
                        parsed["provider"] = "NVIDIA NIM (llama-3.1-nemotron-70b-instruct)"
                        return parsed
        except Exception:
            pass

    # 4. Deterministic Fallback
    return _deterministic_explain(payload)


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

    if db_roster.status == "PUBLISHED":
        _create_notification(
            session=session,
            roster_id=roster_id,
            month=month,
            event_type="ENTRY_EDITED",
            message=f"Manual edit on published roster {month}: {payload.employee_id} on {payload.date} -> {payload.status}.",
            actor_role="OPS_MANAGER",
        )

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

    if db_roster.status == "PUBLISHED":
        _create_notification(
            session=session,
            roster_id=roster_id,
            month=month,
            event_type="BACKUP_ASSIGNED",
            message=(
                f"Backup {payload.backup_employee_id} assigned to {payload.brand_id} "
                f"({payload.process_id}) on {payload.date} for published roster {month}."
            ),
            actor_role="OPS_MANAGER",
        )

    return result
