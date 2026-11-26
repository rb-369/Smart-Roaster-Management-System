"""
Read-only Roster Copilot Chat Assistant Router.
Builds a live grounded snapshot from DB + pure engine functions and lets the AI model
actively query read-only tools (Gemini / OpenRouter with 8s per-request timeout),
falling back deterministically when AI providers are unavailable.
"""
import asyncio
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from database import get_session
from engine.auto_resolver import _build_structural_gaps_summary
from engine.bottlenecks import analyze_bottlenecks
from engine.scheduler import WEEKDAY_NAMES, generate_roster, get_month_dates
from models import Pod, Roster
from routers.rosters import _fetch_domain_data, _recalculate_from_db

router = APIRouter(prefix="/api/assistant", tags=["Assistant"])

SYSTEM_PROMPT = (
    "You are the read-only Roster Copilot for the Smart Roster Management System. "
    "ALWAYS call the provided read-only query tools to look up exact employee schedules, "
    "allocations, skills, date gaps, brand rules, pod bottlenecks, or Sunday-off fairness "
    "before answering. Answer concisely using ONLY data returned by your tool calls and "
    "the summary provided. Cite exact employee names, IDs (EMP-XX), brand IDs (BRD-XX), "
    "dates (YYYY-MM-DD), statuses, and backup scores. Never invent people, dates, or numbers. "
    "Give concrete, actionable recommendations."
)

MONTH_ABBR_TO_NUM = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


class ChatHistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class AssistantChatRequest(BaseModel):
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    message: str = Field(..., min_length=1, max_length=2000)
    history: List[ChatHistoryItem] = Field(default_factory=list)


class AssistantChatResponse(BaseModel):
    month: str
    reply: str
    source: Literal["ai", "deterministic_fallback"]
    provider: Optional[str] = None


def _build_live_snapshot(session: Session, month: str) -> Dict[str, Any]:
    """Build a strictly read-only live roster snapshot for `month`."""
    domain = _fetch_domain_data(session)
    pods = [p.model_dump() for p in session.exec(select(Pod)).all()]

    roster_id = f"ROST-{month}"
    db_roster = session.get(Roster, roster_id)
    if db_roster:
        roster_data = _recalculate_from_db(session, db_roster)
    else:
        roster_data = generate_roster(
            month_str=month,
            employees=domain["employees"],
            brands=domain["brands"],
            processes=domain["processes"],
            brand_process_rules=domain["brand_process_rules"],
            allocations=domain["allocations"],
            public_holidays=domain["public_holidays"],
            leaves_and_compoffs=domain["leaves_and_compoffs"],
        )

    entries: List[Dict[str, Any]] = roster_data.get("entries", [])
    conflicts: List[Dict[str, Any]] = roster_data.get("conflicts", [])
    coverage_matrix: List[Dict[str, Any]] = roster_data.get("coverage_matrix", [])
    kpis: Dict[str, Any] = roster_data.get("kpis", {})

    employees = domain["employees"]
    brands = domain["brands"]
    processes = domain["processes"]
    rules = domain["brand_process_rules"]
    allocations = domain["allocations"]
    holidays = domain["public_holidays"]
    leaves = domain["leaves_and_compoffs"]

    emp_map = {e["id"]: e for e in employees}
    brand_map = {b["id"]: b for b in brands}
    proc_map = {p["id"]: p for p in processes}
    pod_map = {p["id"]: p for p in pods}

    month_dates = get_month_dates(month)
    month_date_strs = {d.strftime("%Y-%m-%d") for d in month_dates}
    sunday_dates = {d.strftime("%Y-%m-%d") for d in month_dates if d.weekday() == 6}

    pending_leaves = [l for l in leaves if l.get("status") == "PENDING"]
    month_leaves = [
        {
            "id": l["id"],
            "employee_id": l["employee_id"],
            "employee_name": emp_map.get(l["employee_id"], {}).get("name", l["employee_id"]),
            "start_date": l["start_date"],
            "end_date": l["end_date"],
            "type": l.get("type"),
            "status": l.get("status"),
            "reason": l.get("reason"),
        }
        for l in leaves
        if l.get("start_date", "")[:7] == month or l.get("end_date", "")[:7] == month
    ]

    bottlenecks = analyze_bottlenecks(
        conflicts=conflicts,
        employees=employees,
        brands=brands,
        pods=pods,
    )
    structural_summary = _build_structural_gaps_summary(conflicts, min_score=70)

    hard_conflicts = [c for c in conflicts if c.get("severity") == "HARD" and not c.get("resolved")]
    soft_conflicts = [c for c in conflicts if c.get("severity") == "SOFT" and not c.get("resolved")]

    grouped_hard: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for c in hard_conflicts:
        b_id = c.get("brand_id") or "MULTI"
        p_id = c.get("process_id") or c.get("conflict_type", "GAP")
        key = (b_id, p_id)
        if key not in grouped_hard:
            grouped_hard[key] = {
                "brand_id": c.get("brand_id"),
                "brand_name": c.get("brand_name") or brand_map.get(b_id, {}).get("name"),
                "pod_id": brand_map.get(b_id, {}).get("pod_id"),
                "process_id": c.get("process_id"),
                "process_name": c.get("process_name") or proc_map.get(p_id, {}).get("code"),
                "conflict_type": c.get("conflict_type"),
                "dates": [],
                "top_backups": [],
            }
        grouped_hard[key]["dates"].append(c.get("date"))
        if not grouped_hard[key]["top_backups"] and c.get("suggested_resolutions"):
            grouped_hard[key]["top_backups"] = [
                {
                    "employee_id": r["employee_id"],
                    "name": r["name"],
                    "score": r["score"],
                    "tier": r["tier"],
                }
                for r in c["suggested_resolutions"][:2]
            ]

    for item in grouped_hard.values():
        item["dates"] = sorted(set(d for d in item["dates"] if d))

    # Index entries by (emp_id, date) for O(1) schedule lookup
    entry_by_emp_date: Dict[Tuple[str, str], Dict[str, Any]] = {}
    sunday_off_counts: Counter[str] = Counter()
    emp_status_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    emp_off_dates: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
    emp_dynamic_backups: Dict[str, List[Dict[str, str]]] = defaultdict(list)

    for entry in entries:
        e_id = entry["employee_id"]
        st = entry.get("status", "WORKING")
        d_str = entry.get("date", "")
        if d_str:
            entry_by_emp_date[(e_id, d_str)] = entry
        emp_status_counts[e_id][st] += 1
        if d_str and st in ("WEEKLY_OFF", "PUBLIC_HOLIDAY", "PLANNED_LEAVE", "COMP_OFF"):
            emp_off_dates[e_id][st].append(d_str)
        if d_str in sunday_dates and st == "WEEKLY_OFF":
            sunday_off_counts[e_id] += 1
        if st == "BACKUP_COVERAGE" and entry.get("assigned_brand_id"):
            b_id = entry["assigned_brand_id"]
            p_id = entry.get("assigned_process_id") or ""
            emp_dynamic_backups[e_id].append({
                "date": d_str,
                "brand_id": b_id,
                "brand_name": brand_map.get(b_id, {}).get("name", b_id),
                "process_code": proc_map.get(p_id, {}).get("code", p_id),
            })

    active_emps = [e for e in employees if e.get("active", True)]
    fairness_summary = sorted(
        [
            {
                "employee_id": e["id"],
                "name": e["name"],
                "pod_id": e.get("pod_id"),
                "role": e.get("role"),
                "default_off": WEEKDAY_NAMES[e.get("default_weekly_off", 6)],
                "preferred_off": WEEKDAY_NAMES[e.get("preferred_weekly_off", 6)],
                "weekly_off_rule": e.get("weekly_off_rule", "FIXED"),
                "sunday_offs": sunday_off_counts.get(e["id"], 0),
            }
            for e in active_emps
        ],
        key=lambda x: (x["sunday_offs"], x["employee_id"]),
    )

    month_holidays = [h for h in holidays if h.get("date") in month_date_strs]
    calendar_type_counts = Counter(r.get("calendar_type", "365_DAYS") for r in rules)
    holiday_impacts: List[Dict[str, Any]] = []
    for ph in month_holidays:
        ph_date = ph["date"]
        operating_on_ph = [
            {
                "brand_id": cov["brand_id"],
                "brand_name": cov.get("brand_name"),
                "process_id": cov["process_id"],
                "process_code": cov.get("process_code"),
                "status": cov.get("status"),
                "working_count": cov.get("working_count"),
                "required_staffing": cov.get("required_staffing"),
            }
            for cov in coverage_matrix
            if cov.get("date") == ph_date and cov.get("is_operating")
        ]
        gaps_on_ph = [
            o for o in operating_on_ph if o["status"] in ("UNCOVERED", "UNDERSTAFFED")
        ]
        holiday_impacts.append(
            {
                "date": ph_date,
                "name": ph.get("name"),
                "operating_slots_count": len(operating_on_ph),
                "gaps_on_holiday": gaps_on_ph,
            }
        )

    emp_allocations: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    brand_allocations: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    emp_primary_brands: Dict[str, List[str]] = defaultdict(list)
    for alc in allocations:
        e_id = alc["employee_id"]
        b_id = alc["brand_id"]
        p_id = alc["process_id"]
        a_type = alc.get("allocation_type", "PRIMARY")
        b_name = brand_map.get(b_id, {}).get("name", b_id)
        p_code = proc_map.get(p_id, {}).get("code", p_id)
        emp_name = emp_map.get(e_id, {}).get("name", e_id)
        emp_allocations[e_id].append({
            "brand_id": b_id,
            "brand_name": b_name,
            "process_id": p_id,
            "process_code": p_code,
            "allocation_type": a_type,
        })
        brand_allocations[b_id].append({
            "employee_id": e_id,
            "employee_name": emp_name,
            "process_id": p_id,
            "process_code": p_code,
            "allocation_type": a_type,
        })
        if a_type == "PRIMARY":
            label = f"{b_name} ({b_id})"
            if label not in emp_primary_brands[e_id]:
                emp_primary_brands[e_id].append(label)

    brand_rules_by_brand: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rules:
        b_id = r["brand_id"]
        p_id = r["process_id"]
        brand_rules_by_brand[b_id].append({
            "process_id": p_id,
            "process_code": proc_map.get(p_id, {}).get("code", p_id),
            "calendar_type": r.get("calendar_type"),
            "min_staffing": r.get("min_staffing"),
            "day_min_staffing_overrides": r.get("day_min_staffing_overrides", {}),
        })

    compact_context = {
        "month": month,
        "kpis": {
            "active_headcount": len(active_emps),
            "coverage_percentage": kpis.get("coverage_percentage", 0.0),
            "covered_slots": kpis.get("covered_slots", 0),
            "total_operating_slots": kpis.get("total_operating_slots", 0),
            "hard_conflicts_count": len(hard_conflicts),
            "soft_warnings_count": len(soft_conflicts),
            "pending_leaves_count": len(pending_leaves),
        },
        "bottlenecks": bottlenecks,
        "structural_gaps_summary": structural_summary,
        "operating_calendar_distribution": dict(calendar_type_counts),
        "public_holidays_in_month": [
            {"date": h["date"], "name": h["name"], "operating_slots_count": h["operating_slots_count"], "gaps_count": len(h["gaps_on_holiday"])}
            for h in holiday_impacts
        ],
    }

    return {
        "month": month,
        "compact_context": compact_context,
        "hard_conflicts": hard_conflicts,
        "soft_conflicts": soft_conflicts,
        "employees": active_emps,
        "brands": brands,
        "pods": pods,
        "pod_map": pod_map,
        "brand_map": brand_map,
        "proc_map": proc_map,
        "emp_map": emp_map,
        "entry_by_emp_date": entry_by_emp_date,
        "fairness_summary": fairness_summary,
        "month_leaves": month_leaves,
        "holiday_impacts": holiday_impacts,
        "emp_primary_brands": dict(emp_primary_brands),
        "emp_allocations": dict(emp_allocations),
        "brand_allocations": dict(brand_allocations),
        "brand_rules_by_brand": dict(brand_rules_by_brand),
        "grouped_hard_conflicts": list(grouped_hard.values()),
        "emp_dynamic_backups": dict(emp_dynamic_backups),
        "emp_status_counts": {k: dict(v) for k, v in emp_status_counts.items()},
        "emp_off_dates": {
            k: {st: sorted(ds) for st, ds in v.items()}
            for k, v in emp_off_dates.items()
        },
        "bottlenecks": bottlenecks,
        "structural_summary": structural_summary,
    }


def _extract_dates_from_query(message: str, month: str) -> List[str]:
    """Extract YYYY-MM-DD dates from ISO, 'Dec 25', '17th December', 'Dec 10-11', or 'Christmas'."""
    year_str, _ = month.split("-")
    year = int(year_str)
    found: List[str] = []

    for iso in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", message):
        found.append(iso)

    if "christmas" in message.lower() or "xmas" in message.lower():
        found.append(f"{year}-12-25")

    month_names_re = "|".join(MONTH_ABBR_TO_NUM.keys())

    # Month-first: "Dec 10-11", "December 25"
    p_month_first = re.compile(
        rf"\b({month_names_re})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:\s*[-–to]+\s*(\d{{1,2}})(?:st|nd|rd|th)?)?\b",
        re.IGNORECASE,
    )
    for m_name, d1_s, d2_s in p_month_first.findall(message):
        m_num = MONTH_ABBR_TO_NUM[m_name.lower()]
        d1 = int(d1_s)
        d2 = int(d2_s) if d2_s else d1
        if d2 < d1:
            d2 = d1
        for day in range(d1, min(d2 + 1, 32)):
            try:
                found.append(datetime(year, m_num, day).strftime("%Y-%m-%d"))
            except ValueError:
                continue

    # Day-first: "17th December", "10-11 Dec", "25th of Dec"
    p_day_first = re.compile(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?(?:\s*[-–to]+\s*(\d{{1,2}})(?:st|nd|rd|th)?)?\s+(?:of\s+)?({month_names_re})\b",
        re.IGNORECASE,
    )
    for d1_s, d2_s, m_name in p_day_first.findall(message):
        m_num = MONTH_ABBR_TO_NUM[m_name.lower()]
        d1 = int(d1_s)
        d2 = int(d2_s) if d2_s else d1
        if d2 < d1:
            d2 = d1
        for day in range(d1, min(d2 + 1, 32)):
            try:
                found.append(datetime(year, m_num, day).strftime("%Y-%m-%d"))
            except ValueError:
                continue

    dedup: List[str] = []
    for d in found:
        if d not in dedup:
            dedup.append(d)
    return dedup


def _match_employee(q: str, employees: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Match employee by @id, id, full name, or unambiguous first/last name token."""
    ql = q.lower()
    for e in employees:
        if e["id"].lower() in ql or e["name"].lower() in ql:
            return e
    tokens = set(re.findall(r"[a-z0-9]+", ql))
    for e in employees:
        parts = [p for p in re.findall(r"[a-z0-9]+", e["name"].lower()) if len(p) >= 3]
        if any(p in tokens for p in parts):
            return e
    return None


def _match_brand(q: str, brands: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Match brand by /id, id, full name, or unambiguous brand name token."""
    ql = q.lower()
    for b in brands:
        if b["id"].lower() in ql or b["name"].lower() in ql:
            return b
    tokens = set(re.findall(r"[a-z0-9]+", ql))
    for b in brands:
        parts = [p for p in re.findall(r"[a-z0-9]+", b["name"].lower()) if len(p) >= 4]
        if any(p in tokens for p in parts):
            return b
    return None


def _match_pod(q: str, pods: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    ql = q.lower()
    for p in pods:
        if (
            p["id"].lower() in ql
            or p["id"].lower().replace("-", " ") in ql
            or p["name"].lower() in ql
        ):
            return p
    return None


def _normalize_date_arg(date_str: Optional[str], month: str) -> Optional[str]:
    if not date_str:
        return None
    ds = date_str.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", ds):
        return ds
    extracted = _extract_dates_from_query(ds, month)
    return extracted[0] if extracted else None


# ─── Read-Only AI Query Tools ─────────────────────────────────────────────────

def _tool_get_roster_overview(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return snapshot["compact_context"]


def _tool_get_employee_details(
    snapshot: Dict[str, Any],
    employee_query: str,
    date: Optional[str] = None,
) -> Dict[str, Any]:
    emp = _match_employee(employee_query, snapshot["employees"])
    if not emp:
        return {
            "error": f"No employee matched '{employee_query}'.",
            "available_employees": [
                {"id": e["id"], "name": e["name"], "pod_id": e.get("pod_id")}
                for e in snapshot["employees"]
            ],
        }

    emp_id = emp["id"]
    norm_date = _normalize_date_arg(date, snapshot["month"])
    emp_skills = set(emp.get("skills", []))
    emp_pod = emp.get("pod_id")

    result: Dict[str, Any] = {
        "employee": {
            "id": emp_id,
            "name": emp["name"],
            "pod_id": emp_pod,
            "role": emp.get("role", "ASSOCIATE"),
            "is_floater": emp.get("is_floater", False),
            "skills": emp.get("skills", []),
            "shift": emp.get("shift"),
            "default_weekly_off": WEEKDAY_NAMES[emp.get("default_weekly_off", 6)],
            "preferred_weekly_off": WEEKDAY_NAMES[emp.get("preferred_weekly_off", 6)],
            "weekly_off_rule": emp.get("weekly_off_rule", "FIXED"),
        },
        "allocations": snapshot["emp_allocations"].get(emp_id, []),
        "scheduled_backup_dates": snapshot["emp_dynamic_backups"].get(emp_id, []),
        "monthly_status_counts": snapshot["emp_status_counts"].get(emp_id, {}),
        "off_and_holiday_dates": snapshot["emp_off_dates"].get(emp_id, {}),
        "leaves_in_month": [l for l in snapshot["month_leaves"] if l["employee_id"] == emp_id],
    }

    if norm_date:
        day_entry = snapshot["entry_by_emp_date"].get((emp_id, norm_date))
        day_status = day_entry.get("status", "UNKNOWN") if day_entry else "NOT_IN_ROSTER"
        result["date_check"] = {
            "date": norm_date,
            "status": day_status,
            "assigned_brand_id": day_entry.get("assigned_brand_id") if day_entry else None,
            "assigned_process_id": day_entry.get("assigned_process_id") if day_entry else None,
            "notes": day_entry.get("notes") if day_entry else None,
            "is_free_to_assign_without_swap": day_status == "WORKING" and not (day_entry and day_entry.get("assigned_brand_id")),
        }

        # Find all open HARD coverage gaps on norm_date matching employee's skills (same pod first)
        matching_gaps: List[Dict[str, Any]] = []
        for c in snapshot["hard_conflicts"]:
            if c.get("date") != norm_date:
                continue
            if c.get("conflict_type") not in ("UNCOVERED_BRAND_PROCESS", "INSUFFICIENT_STAFFING"):
                continue
            p_id = c.get("process_id")
            if p_id and emp_skills and p_id not in emp_skills:
                continue
            b_id = c.get("brand_id")
            b_pod = snapshot["brand_map"].get(b_id, {}).get("pod_id")
            matching_gaps.append({
                "brand_id": b_id,
                "brand_name": c.get("brand_name"),
                "pod_id": b_pod,
                "same_pod": b_pod == emp_pod,
                "process_id": p_id,
                "process_name": c.get("process_name"),
                "conflict_type": c.get("conflict_type"),
                "message": c.get("message"),
                "top_recommended_backups": c.get("suggested_resolutions", [])[:2],
            })
        matching_gaps.sort(key=lambda g: (0 if g["same_pod"] else 1, g["brand_id"] or ""))
        result["matching_open_gaps_on_date"] = matching_gaps[:12]

    return result


def _tool_get_gaps_on_date(
    snapshot: Dict[str, Any],
    date: str,
    pod_id: Optional[str] = None,
    brand_query: Optional[str] = None,
) -> Dict[str, Any]:
    norm_date = _normalize_date_arg(date, snapshot["month"])
    if not norm_date:
        return {"error": f"Could not parse date '{date}' in month {snapshot['month']}."}

    matched_brand = _match_brand(brand_query, snapshot["brands"]) if brand_query else None
    holiday_info = next((h for h in snapshot["holiday_impacts"] if h["date"] == norm_date), None)

    gaps: List[Dict[str, Any]] = []
    for c in snapshot["hard_conflicts"]:
        if c.get("date") != norm_date:
            continue
        b_id = c.get("brand_id")
        b_pod = snapshot["brand_map"].get(b_id, {}).get("pod_id")
        if pod_id and b_pod != pod_id.upper():
            continue
        if matched_brand and b_id != matched_brand["id"]:
            continue
        gaps.append({
            "date": norm_date,
            "conflict_type": c.get("conflict_type"),
            "brand_id": b_id,
            "brand_name": c.get("brand_name"),
            "pod_id": b_pod,
            "process_id": c.get("process_id"),
            "process_name": c.get("process_name"),
            "employee_id": c.get("employee_id"),
            "message": c.get("message"),
            "suggested_resolutions": c.get("suggested_resolutions", [])[:3],
        })

    # Available WORKING floaters on norm_date (useful for assignment questions!)
    working_floaters = [
        {
            "employee_id": e["id"],
            "name": e["name"],
            "pod_id": e.get("pod_id"),
            "skills": e.get("skills", []),
            "status": snapshot["entry_by_emp_date"].get((e["id"], norm_date), {}).get("status", "UNKNOWN"),
            "assigned_brand_id": snapshot["entry_by_emp_date"].get((e["id"], norm_date), {}).get("assigned_brand_id"),
        }
        for e in snapshot["employees"]
        if e.get("is_floater")
    ]

    return {
        "date": norm_date,
        "public_holiday": (
            {"name": holiday_info["name"], "operating_slots_count": holiday_info["operating_slots_count"]}
            if holiday_info
            else None
        ),
        "hard_gaps_count": len(gaps),
        "hard_gaps": gaps[:20],
        "floaters_status_on_date": working_floaters,
    }


def _tool_get_brand_details(snapshot: Dict[str, Any], brand_query: str) -> Dict[str, Any]:
    brand = _match_brand(brand_query, snapshot["brands"])
    if not brand:
        return {
            "error": f"No brand matched '{brand_query}'.",
            "available_brands": [{"id": b["id"], "name": b["name"]} for b in snapshot["brands"]],
        }
    b_id = brand["id"]
    b_conflicts = [g for g in snapshot["grouped_hard_conflicts"] if g.get("brand_id") == b_id]
    return {
        "brand": brand,
        "rules": snapshot["brand_rules_by_brand"].get(b_id, []),
        "allocations": snapshot["brand_allocations"].get(b_id, []),
        "grouped_hard_conflicts": b_conflicts,
    }


def _tool_get_pod_bottlenecks(
    snapshot: Dict[str, Any],
    pod_query: Optional[str] = None,
) -> Dict[str, Any]:
    pod = _match_pod(pod_query, snapshot["pods"]) if pod_query else None
    top_pods = snapshot["bottlenecks"].get("top_pods", [])
    pod_id = pod["id"] if pod else (top_pods[0]["pod_id"] if top_pods else None)
    pod_floaters = [
        {"id": e["id"], "name": e["name"], "skills": e.get("skills", [])}
        for e in snapshot["employees"]
        if e.get("pod_id") == pod_id and e.get("is_floater")
    ]
    pod_brand_gaps = [
        g for g in snapshot["grouped_hard_conflicts"] if g.get("pod_id") == pod_id
    ]
    return {
        "bottlenecks": snapshot["bottlenecks"],
        "focused_pod_id": pod_id,
        "focused_pod_floaters": pod_floaters,
        "focused_pod_brand_gaps": pod_brand_gaps,
        "structural_gaps_summary": snapshot["structural_summary"],
    }


def _tool_get_fairness_and_leaves(
    snapshot: Dict[str, Any],
    employee_query: Optional[str] = None,
) -> Dict[str, Any]:
    fairness = snapshot["fairness_summary"]
    if employee_query:
        emp = _match_employee(employee_query, snapshot["employees"])
        if emp:
            fairness = [f for f in fairness if f["employee_id"] == emp["id"]]
    return {
        "month": snapshot["month"],
        "sunday_off_fairness_lowest_first": fairness[:15],
        "leaves_and_compoffs_in_month": snapshot["month_leaves"],
    }


def _execute_tool(name: str, args: Dict[str, Any], snapshot: Dict[str, Any]) -> Dict[str, Any]:
    if name == "get_roster_overview":
        return _tool_get_roster_overview(snapshot)
    if name == "get_employee_details":
        return _tool_get_employee_details(
            snapshot,
            employee_query=str(args.get("employee_query", "")),
            date=args.get("date"),
        )
    if name == "get_gaps_on_date":
        return _tool_get_gaps_on_date(
            snapshot,
            date=str(args.get("date", "")),
            pod_id=args.get("pod_id"),
            brand_query=args.get("brand_query"),
        )
    if name == "get_brand_details":
        return _tool_get_brand_details(snapshot, brand_query=str(args.get("brand_query", "")))
    if name == "get_pod_bottlenecks":
        return _tool_get_pod_bottlenecks(snapshot, pod_query=args.get("pod_query"))
    if name == "get_fairness_and_leaves":
        return _tool_get_fairness_and_leaves(snapshot, employee_query=args.get("employee_query"))
    return {"error": f"Unknown tool '{name}'"}


GEMINI_FUNCTION_DECLARATIONS = [
    {
        "name": "get_roster_overview",
        "description": "Get overall monthly KPIs, coverage percentage, top bottleneck pods/brands, structural gaps, and holiday summary.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_employee_details",
        "description": "Look up a specific employee's pod, role, floater flag, skills, primary/backup brand allocations, off/holiday dates, leaves, and (if date provided) their exact status and skill-matching open coverage gaps on that date.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "employee_query": {"type": "STRING", "description": "Employee ID (e.g. EMP-30) or name (e.g. Omkar Bhosale)"},
                "date": {"type": "STRING", "description": "Optional date (YYYY-MM-DD or e.g. '2026-12-17') to check their status and assignable gaps on that date"},
            },
            "required": ["employee_query"],
        },
    },
    {
        "name": "get_gaps_on_date",
        "description": "List all uncovered/understaffed hard coverage gaps on a specific date (e.g. Dec 25 Christmas or Dec 17) with ranked backup candidates and floater availability.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date": {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "pod_id": {"type": "STRING", "description": "Optional pod filter like POD-1"},
                "brand_query": {"type": "STRING", "description": "Optional brand ID or name filter"},
            },
            "required": ["date"],
        },
    },
    {
        "name": "get_brand_details",
        "description": "Get a brand/company's pod, operating calendar rules, primary/backup assigned staff, and hard conflict dates.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "brand_query": {"type": "STRING", "description": "Brand ID (e.g. BRD-02) or brand name"},
            },
            "required": ["brand_query"],
        },
    },
    {
        "name": "get_pod_bottlenecks",
        "description": "Analyze why a pod has conflicts, listing its brands with gaps, floater headcount, and hiring/cross-training recommendations.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "pod_query": {"type": "STRING", "description": "Optional Pod ID (e.g. POD-1) or pod name"},
            },
        },
    },
    {
        "name": "get_fairness_and_leaves",
        "description": "Get employee Sunday-off counts (sorted fewest first) and monthly leaves/comp-offs.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "employee_query": {"type": "STRING", "description": "Optional employee ID or name filter"},
            },
        },
    },
]

OPENAI_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": decl["name"],
            "description": decl["description"],
            "parameters": {
                "type": "object",
                "properties": {
                    k: {"type": v["type"].lower(), "description": v.get("description", "")}
                    for k, v in decl["parameters"].get("properties", {}).items()
                },
                **(
                    {"required": decl["parameters"]["required"]}
                    if "required" in decl["parameters"]
                    else {}
                ),
            },
        },
    }
    for decl in GEMINI_FUNCTION_DECLARATIONS
]


# ─── Deterministic Fallback ───────────────────────────────────────────────────

def _format_backups(backups: List[Dict[str, Any]], limit: int = 2) -> str:
    if not backups:
        return "No eligible backup available"
    parts = [
        f"{b['name']} ({b['employee_id']}, Score {b['score']}, {b['tier'].replace('_', ' ')})"
        for b in backups[:limit]
    ]
    return "; ".join(parts)


def _deterministic_reply(message: str, snapshot: Dict[str, Any]) -> str:
    """Fallback handler when LLM providers are unavailable or time out."""
    q = message.lower()
    ctx = snapshot["compact_context"]
    kpis = ctx["kpis"]
    hard_conflicts: List[Dict[str, Any]] = snapshot["hard_conflicts"]
    employees: List[Dict[str, Any]] = snapshot["employees"]
    brands: List[Dict[str, Any]] = snapshot["brands"]
    pods: List[Dict[str, Any]] = snapshot["pods"]
    bottlenecks: Dict[str, Any] = snapshot["bottlenecks"]

    mentioned_dates = _extract_dates_from_query(message, ctx["month"])
    matched_emp = _match_employee(q, employees)
    matched_brand = _match_brand(q, brands)
    matched_pod = _match_pod(q, pods)

    # 1. Employee query
    if matched_emp:
        emp_id = matched_emp["id"]
        emp_name = matched_emp["name"]
        target_date = mentioned_dates[0] if mentioned_dates else None
        details = _tool_get_employee_details(snapshot, emp_id, date=target_date)

        is_where_assign_q = any(w in q for w in ("where", "assign", "deploy", "use", "put", "available"))
        is_company_q = any(
            w in q
            for w in (
                "company", "companies", "brand", "brands", "assigned",
                "allocation", "allocated", "client", "clients",
            )
        )
        is_cover_q = bool(mentioned_dates) or any(
            w in q for w in ("cover", "backup", "gap", "shortfall", "conflict")
        )
        is_holiday_q = any(
            w in q
            for w in (
                "holiday", "holidays", "off", "offs", "leave", "leaves",
                "comp-off", "comp off", "absent", "when", "how many", "schedule",
            )
        )

        # 1a. Where can I assign employee on <date>?
        if target_date and is_where_assign_q:
            dc = details.get("date_check", {})
            gaps = details.get("matching_open_gaps_on_date", [])
            status_str = dc.get("status", "UNKNOWN")
            lines = [
                f"**{emp_name} ({emp_id})** on `{target_date}` — Status: `{status_str}` "
                f"(Pod `{matched_emp.get('pod_id')}`, skills: `{', '.join(matched_emp.get('skills', []))}`)."
            ]
            if status_str == "WEEKLY_OFF":
                lines.append(
                    f"- Note: `{target_date}` is {emp_name}'s scheduled Weekly Off (`WO`). "
                    f"Swapping or overriding their weekly off allows assignment to these matching hard gaps:"
                )
            elif dc.get("assigned_brand_id"):
                lines.append(f"- Already assigned to `{dc['assigned_brand_id']}` ({dc.get('assigned_process_id')}).")
            if gaps:
                for g in gaps[:5]:
                    scope = "Same pod" if g["same_pod"] else f"Cross-pod ({g['pod_id']})"
                    lines.append(
                        f"  - **{g['brand_name']} ({g['brand_id']})** · `{g['process_name']}` ({scope}) — {g['conflict_type']}"
                    )
            else:
                lines.append(f"- No open skill-matching hard gaps exist on `{target_date}`.")
            return "\n".join(lines)

        # 1b. Which company/brand is employee assigned to?
        if is_company_q and not is_cover_q and not is_holiday_q:
            role_tag = "Floater" if matched_emp.get("is_floater") else matched_emp.get("role", "ASSOCIATE")
            lines = [f"**{emp_name} ({emp_id})** — Pod `{matched_emp.get('pod_id')}` · Role: `{role_tag}`"]
            alcs = details.get("allocations", [])
            prim = [a for a in alcs if a["allocation_type"] == "PRIMARY"]
            bkp = [a for a in alcs if a["allocation_type"] == "BACKUP"]
            if prim:
                prim_grouped: Dict[str, List[str]] = defaultdict(list)
                for a in prim:
                    prim_grouped[f"{a['brand_name']} ({a['brand_id']})"].append(a["process_code"])
                lines.append("- **Primary Assignments:**")
                for b_lbl, procs in prim_grouped.items():
                    lines.append(f"  - **{b_lbl}** (`{', '.join(procs)}`)")
            else:
                lines.append("- **Primary Assignments:** None (dedicated Pod Floater)")
            if bkp:
                bkp_grouped: Dict[str, List[str]] = defaultdict(list)
                for a in bkp:
                    bkp_grouped[f"{a['brand_name']} ({a['brand_id']})"].append(a["process_code"])
                lines.append("- **Configured Backup Assignments:**")
                for b_lbl, procs in bkp_grouped.items():
                    lines.append(f"  - **{b_lbl}** (`{', '.join(procs)}`)")
            dyn = details.get("scheduled_backup_dates", [])
            if dyn:
                by_brand: Dict[str, List[str]] = defaultdict(list)
                for db in dyn:
                    by_brand[f"{db['brand_name']} ({db['brand_id']}) · {db['process_code']}"].append(db["date"])
                lines.append(f"- **Scheduled Backup Coverage in {ctx['month']}:**")
                for lbl, ds in by_brand.items():
                    lines.append(f"  - **{lbl}**: {', '.join(sorted(ds))}")
            return "\n".join(lines)

        # 1c. Cover / backup / gaps on dates
        if is_cover_q:
            primary_brands = snapshot["emp_primary_brands"].get(emp_id, [])
            emp_brand_ids = {b_lbl.split("(")[-1].rstrip(")") for b_lbl in primary_brands}
            emp_leaves = details.get("leaves_in_month", [])
            relevant_conflicts = [
                c
                for c in hard_conflicts
                if (not mentioned_dates or c.get("date") in mentioned_dates)
                and (c.get("employee_id") == emp_id or c.get("brand_id") in emp_brand_ids)
            ]
            lines = [
                f"**{emp_name} ({emp_id})** — Pod `{matched_emp.get('pod_id')}`, Primary brands: "
                + (", ".join(primary_brands) if primary_brands else "Floater / No primary brand")
            ]
            if emp_leaves:
                lv_str = ", ".join(
                    f"{l['id']} ({l['start_date']} to {l['end_date']}, {l['status']})"
                    for l in emp_leaves
                )
                lines.append(f"- **Leaves/Comp-offs:** {lv_str}")
            if relevant_conflicts:
                lines.append(f"- **Hard coverage gaps ({len(relevant_conflicts)}):**")
                seen_keys = set()
                for c in relevant_conflicts[:8]:
                    b_id = c.get("brand_id") or "MULTI"
                    p_id = c.get("process_id") or c.get("conflict_type")
                    d_str = c.get("date")
                    key = (d_str, b_id, p_id)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    b_label = f"{c.get('brand_name') or b_id} ({b_id})" if c.get("brand_id") else "Multi-brand"
                    backups_str = _format_backups(c.get("suggested_resolutions", []), limit=2)
                    lines.append(f"  - `{d_str}` — **{b_label}** / {c.get('process_name') or p_id}: Top backups → {backups_str}")
            else:
                date_note = f" on {', '.join(mentioned_dates)}" if mentioned_dates else ""
                lines.append(f"- No unresolved hard coverage gaps found for {emp_name}{date_note}.")
            return "\n".join(lines)

        # 1d. Holidays / Weekly offs / Leaves / Schedule
        st_counts = details.get("monthly_status_counts", {})
        off_dates_map = details.get("off_and_holiday_dates", {})
        emp_leaves = details.get("leaves_in_month", [])
        lines = [f"**{emp_name} ({emp_id})** — {ctx['month']} Offs & Holidays:"]
        if st_counts:
            lines.append(
                f"- **Counts:** {st_counts.get('WEEKLY_OFF', 0)} Weekly Off (`WO`), "
                f"{st_counts.get('PUBLIC_HOLIDAY', 0)} Public Holiday (`PH`), "
                f"{st_counts.get('PLANNED_LEAVE', 0)} Planned Leave (`LV`), "
                f"{st_counts.get('COMP_OFF', 0)} Comp-Off (`CO`) "
                f"({st_counts.get('WORKING', 0)} Working, {st_counts.get('BACKUP_COVERAGE', 0)} Backup)."
            )
        if off_dates_map.get("WEEKLY_OFF"):
            lines.append(f"- **Weekly Off Dates:** {', '.join(off_dates_map['WEEKLY_OFF'])}")
        if off_dates_map.get("PUBLIC_HOLIDAY"):
            lines.append(f"- **Public Holiday Dates:** {', '.join(off_dates_map['PUBLIC_HOLIDAY'])}")
        if emp_leaves:
            lv_str = ", ".join(
                f"{l['id']} ({l['type']}, {l['start_date']} to {l['end_date']}, {l['status']})"
                for l in emp_leaves
            )
            lines.append(f"- **Leaves/Comp-offs:** {lv_str}")
        else:
            lines.append(f"- **Leaves/Comp-offs:** None recorded in {ctx['month']}.")
        return "\n".join(lines)

    # 2. Christmas / Specific Date(s) query
    if mentioned_dates:
        lines: List[str] = []
        holiday_map = {h["date"]: h for h in snapshot["holiday_impacts"]}
        for d_str in mentioned_dates[:4]:
            ph = holiday_map.get(d_str)
            date_conflicts = [
                c
                for c in hard_conflicts
                if c.get("date") == d_str and c.get("conflict_type") in ("UNCOVERED_BRAND_PROCESS", "INSUFFICIENT_STAFFING")
            ]
            if ph:
                lines.append(
                    f"**{d_str} ({ph['name']})**: {ph['operating_slots_count']} brand-process slot(s) operate (`365_DAYS` calendar); "
                    f"brands on `DAILY_EXCEPT_PH` / `MON_SAT_EXCEPT_PH` are closed. "
                    f"**{len(date_conflicts)} hard gap(s)** detected:"
                )
            else:
                lines.append(f"**{d_str}**: **{len(date_conflicts)} hard coverage gap(s)** detected:")
            if date_conflicts:
                for c in date_conflicts[:10]:
                    b_id = c.get("brand_id")
                    b_name = c.get("brand_name") or b_id
                    p_name = c.get("process_name") or c.get("process_id")
                    backups_str = _format_backups(c.get("suggested_resolutions", []), limit=2)
                    lines.append(f"- **{b_name} ({b_id})** · `{p_name}` — Top backups: {backups_str}")
            else:
                lines.append("- All operating brand-processes are covered on this date.")
        return "\n".join(lines)

    # 3. Sunday-off fairness query
    if "sunday" in q or "fairness" in q or "fewest" in q:
        fairness = snapshot["fairness_summary"]
        min_count = fairness[0]["sunday_offs"] if fairness else 0
        lowest = [f for f in fairness if f["sunday_offs"] <= min_count + 1][:8]
        lines = [
            f"**Sunday Off Fairness Summary ({ctx['month']}):**",
            f"Lowest Sunday weekly-off count is **{min_count}**:",
        ]
        for f in lowest:
            lines.append(
                f"- **{f['name']} ({f['employee_id']})** ({f['pod_id']}, {f['weekly_off_rule']}): "
                f"**{f['sunday_offs']}** Sunday off(s) · Default off: {f['default_off']}, Preferred off: {f['preferred_off']}"
            )
        return "\n".join(lines)

    # 4. Pod query
    if matched_pod or "bottleneck" in q or "pod" in q:
        top_pods = bottlenecks.get("top_pods", [])
        target_pod = None
        if matched_pod:
            target_pod = next((tp for tp in top_pods if tp["pod_id"] == matched_pod["id"]), None)
        elif top_pods:
            target_pod = top_pods[0]

        if target_pod:
            pod_id = target_pod["pod_id"]
            pod_brands_conflicts = [
                g for g in snapshot["grouped_hard_conflicts"] if g.get("pod_id") == pod_id
            ]
            pod_recs = [r for r in bottlenecks.get("recommendations", []) if pod_id in r]
            lines = [
                f"**{target_pod['pod_name']} ({pod_id})** accounts for **{target_pod['hard_conflicts_count']}** of "
                f"**{bottlenecks.get('total_hard_conflicts', kpis['hard_conflicts_count'])}** hard conflicts "
                f"(**{target_pod['share_percentage']}%**) across **{target_pod['affected_brands_count']}** brand(s) "
                f"on **{target_pod['distinct_gap_dates']}** distinct date(s)."
            ]
            if pod_brands_conflicts:
                lines.append("- **Primary gap drivers:**")
                for g in pod_brands_conflicts[:5]:
                    backups_str = _format_backups(g.get("top_backups", []), limit=2)
                    lines.append(
                        f"  - **{g['brand_name']} ({g['brand_id']})** · `{g['process_name']}` ({len(g['dates'])} day(s)) — {backups_str}"
                    )
            if pod_recs:
                lines.append(f"- **Recommendation:** {pod_recs[0]}")
            return "\n".join(lines)

    # 5. Brand query
    if matched_brand:
        b_id = matched_brand["id"]
        is_team_q = any(w in q for w in ("who", "employee", "employees", "assigned", "staff", "team", "owner", "backup"))
        b_alcs = snapshot.get("brand_allocations", {}).get(b_id, [])
        b_groups = [g for g in snapshot["grouped_hard_conflicts"] if g.get("brand_id") == b_id]
        lines = [f"**{matched_brand['name']} ({b_id})** (Pod `{matched_brand.get('pod_id')}`):"]
        if is_team_q and b_alcs:
            for a in b_alcs:
                lines.append(
                    f"- **{a['employee_name']} ({a['employee_id']})** · `{a['process_code']}` ({a['allocation_type']})"
                )
            if not any(w in q for w in ("gap", "conflict", "shortfall")):
                return "\n".join(lines)
        if b_groups:
            for g in b_groups:
                backups_str = _format_backups(g.get("top_backups", []), limit=2)
                lines.append(
                    f"- `{g['process_name']}`: **{len(g['dates'])}** hard conflict date(s) "
                    f"({', '.join(g['dates'][:5])}{'...' if len(g['dates']) > 5 else ''}). Top backups → {backups_str}"
                )
        else:
            lines.append("- Currently has **0 unresolved hard conflicts** in this month.")
        return "\n".join(lines)

    # 6. General live ops overview
    top_pods = bottlenecks.get("top_pods", [])
    top_pod_line = (
        f"{top_pods[0]['pod_name']} ({top_pods[0]['pod_id']}: {top_pods[0]['hard_conflicts_count']} hard)"
        if top_pods
        else "None"
    )
    recs = bottlenecks.get("recommendations", [])
    lines = [
        f"**Live Roster Snapshot ({ctx['month']}):**",
        f"- **Coverage:** {kpis['coverage_percentage']}% ({kpis['covered_slots']}/{kpis['total_operating_slots']} slots) · Active headcount: {kpis['active_headcount']}",
        f"- **Conflicts:** {kpis['hard_conflicts_count']} hard, {kpis['soft_warnings_count']} soft warnings · Pending leaves: {kpis['pending_leaves_count']}",
        f"- **Top Bottleneck Pod:** {top_pod_line}",
        f"- **Structural Summary:** {snapshot['structural_summary']}",
    ]
    if recs:
        lines.append(f"- **Top Recommendation:** {recs[0]}")
    return "\n".join(lines)


# ─── Agentic Tool-Calling LLM Runners ─────────────────────────────────────────

async def _run_gemini_with_tools(
    month: str,
    message: str,
    history: List[ChatHistoryItem],
    snapshot: Dict[str, Any],
) -> Optional[Tuple[str, str]]:
    """Call Gemini 2.5 Flash with read-only function calling tools (8s timeout per HTTP call)."""
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        return None

    overview_json = json.dumps(snapshot["compact_context"], separators=(",", ":"))
    contents: List[Dict[str, Any]] = []
    for item in history[-6:]:
        role = "model" if item.role == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": item.content}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={gemini_key}"
    )

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            for _ in range(4):
                resp = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={
                        "systemInstruction": {
                            "parts": [
                                {
                                    "text": (
                                        f"{SYSTEM_PROMPT}\n\n"
                                        f"ACTIVE_MONTH: {month}\n"
                                        f"OVERVIEW_KPI_SUMMARY: {overview_json}"
                                    )
                                }
                            ]
                        },
                        "contents": contents,
                        "tools": [{"functionDeclarations": GEMINI_FUNCTION_DECLARATIONS}],
                        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 700},
                    },
                )
                if resp.status_code != 200:
                    return None

                data = resp.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    return None
                model_content = candidates[0].get("content", {})
                parts = model_content.get("parts", [])
                if not parts:
                    return None

                fn_calls = [p["functionCall"] for p in parts if "functionCall" in p]
                if not fn_calls:
                    text_parts = [p.get("text", "") for p in parts if p.get("text")]
                    final_text = "\n".join(text_parts).strip()
                    return (final_text, "Gemini (gemini-2.5-flash)") if final_text else None

                # Append model turn (preserving thoughtSignature) and execute read-only tools
                contents.append({"role": "model", "parts": parts})
                fn_response_parts = []
                for fc in fn_calls:
                    fn_name = fc.get("name", "")
                    fn_args = fc.get("args", {}) or {}
                    tool_result = _execute_tool(fn_name, fn_args, snapshot)
                    fn_response_parts.append(
                        {
                            "functionResponse": {
                                "name": fn_name,
                                "response": {"result": tool_result},
                            }
                        }
                    )
                contents.append({"role": "user", "parts": fn_response_parts})
    except (httpx.TimeoutException, Exception):
        return None

    return None


async def _run_openrouter_with_tools(
    month: str,
    message: str,
    history: List[ChatHistoryItem],
    snapshot: Dict[str, Any],
) -> Optional[Tuple[str, str]]:
    """Call OpenRouter with read-only function calling tools (8s timeout per HTTP call)."""
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not openrouter_key:
        return None

    overview_json = json.dumps(snapshot["compact_context"], separators=(",", ":"))
    messages_payload: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                f"{SYSTEM_PROMPT}\n\n"
                f"ACTIVE_MONTH: {month}\n"
                f"OVERVIEW_KPI_SUMMARY: {overview_json}"
            ),
        }
    ]
    for item in history[-6:]:
        messages_payload.append({"role": item.role, "content": item.content})
    messages_payload.append({"role": "user", "content": message})

    model_name = "nvidia/nemotron-3-ultra-550b-a55b:free"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            for _ in range(4):
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openrouter_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model_name,
                        "messages": messages_payload,
                        "tools": OPENAI_TOOLS_SCHEMA,
                        "reasoning": {"effort": "low"},
                        "temperature": 0.1,
                        "max_tokens": 700,
                    },
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
                msg = data.get("choices", [{}])[0].get("message", {})
                tool_calls = msg.get("tool_calls") or []
                if not tool_calls:
                    content = (msg.get("content") or "").strip()
                    return (content, f"OpenRouter ({model_name})") if content else None

                messages_payload.append(msg)
                for tc in tool_calls:
                    fn_info = tc.get("function", {})
                    fn_name = fn_info.get("name", "")
                    try:
                        fn_args = json.loads(fn_info.get("arguments") or "{}")
                    except Exception:
                        fn_args = {}
                    tool_result = _execute_tool(fn_name, fn_args, snapshot)
                    messages_payload.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id", fn_name),
                            "content": json.dumps(tool_result, separators=(",", ":")),
                        }
                    )
    except (httpx.TimeoutException, Exception):
        return None

    return None


@router.post("/chat", response_model=AssistantChatResponse)
async def assistant_chat(
    payload: AssistantChatRequest,
    session: Session = Depends(get_session),
):
    """
    Strictly read-only Roster Copilot endpoint.
    Lets the AI model query live read-only tools (Gemini -> OpenRouter) before answering,
    with deterministic Python fallback if AI providers time out or are unconfigured.
    """
    snapshot = _build_live_snapshot(session, payload.month)

    ai_result: Optional[Tuple[str, str]] = None
    try:
        ai_result = await asyncio.wait_for(
            _run_gemini_with_tools(
                month=payload.month,
                message=payload.message,
                history=payload.history,
                snapshot=snapshot,
            ),
            timeout=10.0,
        )
    except (asyncio.TimeoutError, Exception):
        ai_result = None

    if ai_result is None:
        try:
            ai_result = await asyncio.wait_for(
                _run_openrouter_with_tools(
                    month=payload.month,
                    message=payload.message,
                    history=payload.history,
                    snapshot=snapshot,
                ),
                timeout=10.0,
            )
        except (asyncio.TimeoutError, Exception):
            ai_result = None

    if ai_result is not None:
        reply_text, provider_name = ai_result
        return AssistantChatResponse(
            month=payload.month,
            reply=reply_text,
            source="ai",
            provider=provider_name,
        )

    fallback_reply = _deterministic_reply(payload.message, snapshot)
    return AssistantChatResponse(
        month=payload.month,
        reply=fallback_reply,
        source="deterministic_fallback",
        provider="Deterministic Engine",
    )
