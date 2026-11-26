"""
Read-only Roster Copilot Chat Assistant Router.
Builds a live grounded snapshot from DB + pure engine functions and answers
using OpenRouter (8s timeout) with a deterministic Python fallback.
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
    "Answer concisely using ONLY the provided live roster data. "
    "Cite exact employee names, brand IDs, dates, and backup scores. "
    "Never invent people, dates, or numbers. Give concrete recommendations."
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
    """Build a compact, strictly read-only live roster snapshot for `month`."""
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

    # Pending leaves count
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

    # Bottlenecks & structural gap summary
    bottlenecks = analyze_bottlenecks(
        conflicts=conflicts,
        employees=employees,
        brands=brands,
        pods=pods,
    )
    structural_summary = _build_structural_gaps_summary(conflicts, min_score=70)

    # Hard conflicts grouped concisely by (brand_id, process_id) + top 2 backups
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

    # Employee fairness summary (Sunday offs + weekly off rule + status counts + off dates)
    sunday_off_counts: Counter[str] = Counter()
    emp_status_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    emp_off_dates: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
    for entry in entries:
        e_id = entry["employee_id"]
        st = entry.get("status", "WORKING")
        d_str = entry.get("date")
        emp_status_counts[e_id][st] += 1
        if d_str and st in ("WEEKLY_OFF", "PUBLIC_HOLIDAY", "PLANNED_LEAVE", "COMP_OFF"):
            emp_off_dates[e_id][st].append(d_str)
        if d_str in sunday_dates and st == "WEEKLY_OFF":
            sunday_off_counts[e_id] += 1

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

    # Operating calendar differences & holidays in month
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

    # Primary brand allocations per employee (for quick lookup)
    emp_primary_brands: Dict[str, List[str]] = defaultdict(list)
    for alc in allocations:
        if alc.get("allocation_type") == "PRIMARY":
            b_id = alc["brand_id"]
            b_name = brand_map.get(b_id, {}).get("name", b_id)
            label = f"{b_name} ({b_id})"
            if label not in emp_primary_brands[alc["employee_id"]]:
                emp_primary_brands[alc["employee_id"]].append(label)

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
        "grouped_hard_conflicts": list(grouped_hard.values()),
        "month_leaves": month_leaves,
        "employee_sunday_off_fairness_lowest_first": fairness_summary[:12],
        "operating_calendar_distribution": dict(calendar_type_counts),
        "public_holidays_in_month": holiday_impacts,
    }

    return {
        "compact_context": compact_context,
        "hard_conflicts": hard_conflicts,
        "soft_conflicts": soft_conflicts,
        "employees": active_emps,
        "brands": brands,
        "pods": pods,
        "pod_map": pod_map,
        "brand_map": brand_map,
        "emp_map": emp_map,
        "fairness_summary": fairness_summary,
        "month_leaves": month_leaves,
        "holiday_impacts": holiday_impacts,
        "emp_primary_brands": dict(emp_primary_brands),
        "emp_status_counts": {k: dict(v) for k, v in emp_status_counts.items()},
        "emp_off_dates": {
            k: {st: sorted(ds) for st, ds in v.items()}
            for k, v in emp_off_dates.items()
        },
        "bottlenecks": bottlenecks,
        "structural_summary": structural_summary,
    }


def _extract_dates_from_query(message: str, month: str) -> List[str]:
    """Extract YYYY-MM-DD dates mentioned as ISO, 'Dec 25', 'Dec 10-11', or 'Christmas'."""
    year_str, month_num_str = month.split("-")
    year = int(year_str)
    found: List[str] = []

    # 1. Explicit ISO dates
    for iso in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", message):
        found.append(iso)

    # 2. Christmas keyword
    if "christmas" in message.lower() or "xmas" in message.lower():
        found.append(f"{year}-12-25")

    # 3. Month name + day or day range: e.g. "Dec 10-11", "Dec 10–11", "December 25"
    pattern = re.compile(
        r"\b(" + "|".join(MONTH_ABBR_TO_NUM.keys()) + r")\s+(\d{1,2})(?:\s*[-–to]+\s*(\d{1,2}))?\b",
        re.IGNORECASE,
    )
    for m_name, d1_s, d2_s in pattern.findall(message):
        m_num = MONTH_ABBR_TO_NUM[m_name.lower()]
        d1 = int(d1_s)
        d2 = int(d2_s) if d2_s else d1
        if d2 < d1:
            d2 = d1
        for day in range(d1, min(d2 + 1, 32)):
            try:
                dt = datetime(year, m_num, day)
                found.append(dt.strftime("%Y-%m-%d"))
            except ValueError:
                continue

    # Deduplicate preserving order
    dedup: List[str] = []
    for d in found:
        if d not in dedup:
            dedup.append(d)
    return dedup


def _format_backups(backups: List[Dict[str, Any]], limit: int = 2) -> str:
    if not backups:
        return "No eligible backup available"
    parts = [
        f"{b['name']} ({b['employee_id']}, Score {b['score']}, {b['tier'].replace('_', ' ')})"
        for b in backups[:limit]
    ]
    return "; ".join(parts)


def _match_employee(q: str, employees: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Match employee by @id, id, full name, or unambiguous first/last name token."""
    for e in employees:
        if e["id"].lower() in q or e["name"].lower() in q:
            return e
    tokens = set(re.findall(r"[a-z0-9]+", q))
    for e in employees:
        parts = [p for p in re.findall(r"[a-z0-9]+", e["name"].lower()) if len(p) >= 3]
        if any(p in tokens for p in parts):
            return e
    return None


def _match_brand(q: str, brands: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Match brand by /id, id, full name, or unambiguous brand name token."""
    for b in brands:
        if b["id"].lower() in q or b["name"].lower() in q:
            return b
    tokens = set(re.findall(r"[a-z0-9]+", q))
    for b in brands:
        parts = [p for p in re.findall(r"[a-z0-9]+", b["name"].lower()) if len(p) >= 4]
        if any(p in tokens for p in parts):
            return b
    return None


def _deterministic_reply(message: str, snapshot: Dict[str, Any]) -> str:
    """Answer common operational questions directly from the live grounded snapshot."""
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
    matched_pod = next(
        (
            p
            for p in pods
            if p["id"].lower() in q
            or p["id"].lower().replace("-", " ") in q
            or p["name"].lower() in q
        ),
        None,
    )

    # 1. Employee query (with or without dates: coverage, leaves, holidays, offs)
    if matched_emp:
        emp_id = matched_emp["id"]
        emp_name = matched_emp["name"]
        primary_brands = snapshot["emp_primary_brands"].get(emp_id, [])
        emp_brand_ids = {
            b_lbl.split("(")[-1].rstrip(")") for b_lbl in primary_brands
        }
        emp_leaves = [l for l in snapshot["month_leaves"] if l["employee_id"] == emp_id]
        st_counts = snapshot.get("emp_status_counts", {}).get(emp_id, {})

        relevant_conflicts = [
            c
            for c in hard_conflicts
            if (not mentioned_dates or c.get("date") in mentioned_dates)
            and (c.get("employee_id") == emp_id or c.get("brand_id") in emp_brand_ids)
        ]

        lines = [
            f"**{emp_name} ({emp_id})** — Pod `{matched_emp.get('pod_id')}`, Primary brands: "
            + (", ".join(primary_brands) if primary_brands else "Floater / No primary brand")
            + "."
        ]
        if st_counts:
            lines.append(
                f"- **{ctx['month']} Schedule Breakdown:** "
                f"{st_counts.get('WORKING', 0)} Working (`W`), "
                f"{st_counts.get('WEEKLY_OFF', 0)} Weekly Off (`WO`), "
                f"{st_counts.get('PUBLIC_HOLIDAY', 0)} Public Holiday (`PH`), "
                f"{st_counts.get('PLANNED_LEAVE', 0)} Planned Leave (`LV`), "
                f"{st_counts.get('COMP_OFF', 0)} Comp-Off (`CO`), "
                f"{st_counts.get('BACKUP_COVERAGE', 0)} Backup (`BK`)."
            )
        off_dates_map = snapshot.get("emp_off_dates", {}).get(emp_id, {})
        if off_dates_map.get("WEEKLY_OFF"):
            lines.append(f"- **Weekly Off Dates (`WO`):** {', '.join(off_dates_map['WEEKLY_OFF'])}")
        if off_dates_map.get("PUBLIC_HOLIDAY"):
            lines.append(f"- **Public Holiday Dates (`PH`):** {', '.join(off_dates_map['PUBLIC_HOLIDAY'])}")
        if off_dates_map.get("PLANNED_LEAVE") or off_dates_map.get("COMP_OFF"):
            lv_dates = off_dates_map.get("PLANNED_LEAVE", []) + off_dates_map.get("COMP_OFF", [])
            lines.append(f"- **Leave / Comp-Off Dates:** {', '.join(sorted(lv_dates))}")
        if emp_leaves:
            lv_str = ", ".join(
                f"{l['id']} ({l['type']}, {l['start_date']} to {l['end_date']}, {l['status']})"
                for l in emp_leaves
            )
            lines.append(f"- **Leaves/Comp-offs:** {lv_str}")
        else:
            lines.append(f"- **Leaves/Comp-offs:** None recorded in {ctx['month']}.")

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
        elif mentioned_dates or any(w in q for w in ("cover", "backup", "gap")):
            date_note = f" on {', '.join(mentioned_dates)}" if mentioned_dates else ""
            lines.append(f"- No unresolved hard coverage gaps found for {emp_name}{date_note}.")
        return "\n".join(lines)

    # 2. Christmas / Specific Date(s) query (e.g. "Which brands have gaps on Dec 25 (Christmas)?")
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

    # 4. Pod query (e.g. "Why does Pod 1 have the most conflicts this month?")
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
                g for g in ctx["grouped_hard_conflicts"] if g.get("pod_id") == pod_id
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
        b_groups = [g for g in ctx["grouped_hard_conflicts"] if g.get("brand_id") == b_id]
        lines = [f"**{matched_brand['name']} ({b_id})** (Pod `{matched_brand.get('pod_id')}`):"]
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


async def _call_openrouter(
    month: str,
    message: str,
    history: List[ChatHistoryItem],
    compact_context: Dict[str, Any],
) -> Optional[Tuple[str, str]]:
    """Call OpenRouter with strict 8.0s timeout. Returns (reply, provider) or None on failure."""
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not openrouter_key:
        return None

    context_json = json.dumps(compact_context, separators=(",", ":"))
    messages_payload: List[Dict[str, str]] = [
        {
            "role": "system",
            "content": f"{SYSTEM_PROMPT}\n\nLIVE_ROSTER_DATA ({month}):\n{context_json}",
        }
    ]
    for item in history[-6:]:
        messages_payload.append({"role": item.role, "content": item.content})
    messages_payload.append({"role": "user", "content": message})

    for model_name in ("nvidia/nemotron-3-ultra-550b-a55b:free", "openrouter/free"):
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openrouter_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model_name,
                        "messages": messages_payload,
                        "temperature": 0.1,
                        "max_tokens": 500,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )
                    if content:
                        return content, f"OpenRouter ({model_name})"
        except (httpx.TimeoutException, Exception):
            continue

    return None


@router.post("/chat", response_model=AssistantChatResponse)
async def assistant_chat(
    payload: AssistantChatRequest,
    session: Session = Depends(get_session),
):
    """
    Strictly read-only Roster Copilot endpoint.
    Grounds responses in live DB + deterministic engine state for `payload.month`,
    using OpenRouter (8s timeout) with automatic deterministic Python fallback.
    """
    snapshot = _build_live_snapshot(session, payload.month)

    try:
        ai_result = await asyncio.wait_for(
            _call_openrouter(
                month=payload.month,
                message=payload.message,
                history=payload.history,
                compact_context=snapshot["compact_context"],
            ),
            timeout=8.0,
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
