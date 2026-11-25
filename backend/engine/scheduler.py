"""
Deterministic Monthly Roster Generator and Coverage Engine.
PURE DETERMINISTIC LOGIC - NO FASTAPI OR DATABASE CALLS.
"""
from datetime import date, datetime, timedelta
import calendar
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict

from .calendar_rules import is_operating_day, get_required_staffing
from .validator import validate_roster


WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def get_month_dates(month_str: str) -> List[date]:
    """Given 'YYYY-MM', returns list of date objects for all days in that month."""
    year, month = map(int, month_str.split("-"))
    num_days = calendar.monthrange(year, month)[1]
    return [date(year, month, d) for d in range(1, num_days + 1)]


def generate_roster(
    month_str: str,
    employees: List[Dict[str, Any]],
    brands: List[Dict[str, Any]],
    processes: List[Dict[str, Any]],
    brand_process_rules: List[Dict[str, Any]],
    allocations: List[Dict[str, Any]],
    public_holidays: List[Dict[str, Any]],
    leaves_and_compoffs: List[Dict[str, Any]],
    manual_overrides: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Pure deterministic monthly roster generator.
    
    Steps:
    1. Resolve Demand Calendar per (brand, process, date).
    2. Assign Base Employee Daily Statuses (Leaves, Comp-offs, Public Holidays, Staggered Weekly Offs).
    3. Apply Manual Overrides.
    4. Evaluate Coverage & Auto-Assign Configured Backups.
    5. Run Full Validation Pass (6 checks).
    6. Return entries, coverage_matrix, conflicts, and KPIs.
    """
    month_dates = get_month_dates(month_str)
    date_strs = [d.strftime("%Y-%m-%d") for d in month_dates]

    emp_dict = {e["id"]: e for e in employees}
    brand_dict = {b["id"]: b for b in brands}
    proc_dict = {p["id"]: p for p in processes}

    # Public holidays set for this month
    ph_dict = {ph["date"]: ph for ph in public_holidays}
    ph_dates = set(ph_dict.keys())

    # Map primary allocations: emp_id -> list of rules (brand_id, process_id)
    emp_primary_rules: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    rule_lookup = {(r["brand_id"], r["process_id"]): r for r in brand_process_rules}
    primary_allocations_by_bp: Dict[tuple, List[str]] = defaultdict(list)
    backup_allocations_by_bp: Dict[tuple, List[str]] = defaultdict(list)

    for alc in allocations:
        bp_key = (alc["brand_id"], alc["process_id"])
        if alc.get("allocation_type") == "PRIMARY":
            primary_allocations_by_bp[bp_key].append(alc["employee_id"])
            if bp_key in rule_lookup:
                emp_primary_rules[alc["employee_id"]].append(rule_lookup[bp_key])
        elif alc.get("allocation_type") == "BACKUP":
            backup_allocations_by_bp[bp_key].append(alc["employee_id"])

    # Determine if employee has ANY primary 365_DAYS rule
    emp_has_365_rule: Dict[str, bool] = {}
    for emp_id, rules in emp_primary_rules.items():
        emp_has_365_rule[emp_id] = any(r.get("calendar_type") == "365_DAYS" for r in rules)

    # Approved leaves/compoffs map: (emp_id, date_str) -> leave dict
    approved_leaves_map: Dict[tuple, Dict[str, Any]] = {}
    for lvc in leaves_and_compoffs:
        if lvc.get("status") == "APPROVED":
            s_d = datetime.strptime(lvc["start_date"], "%Y-%m-%d").date()
            e_d = datetime.strptime(lvc["end_date"], "%Y-%m-%d").date()
            cur = s_d
            while cur <= e_d:
                approved_leaves_map[(lvc["employee_id"], cur.strftime("%Y-%m-%d"))] = lvc
                cur += timedelta(days=1)

    # Manual overrides map: (emp_id, date_str) -> override dict
    manual_overrides_map: Dict[tuple, Dict[str, Any]] = {}
    if manual_overrides:
        for mo in manual_overrides:
            manual_overrides_map[(mo["employee_id"], mo["date"])] = mo

    # Weekly off calculation and staggering
    soft_preference_overrides: List[Dict[str, Any]] = []
    emp_effective_off: Dict[str, int] = {}

    # Check multi-resource teams for same-day weekly off conflict
    # If two primary employees on same (brand, process) share same weekly off, stagger rotational ones
    assigned_offs: Dict[str, int] = {}
    for emp in employees:
        assigned_offs[emp["id"]] = emp.get("default_weekly_off", 6)

    for bp_key, emp_ids in primary_allocations_by_bp.items():
        if len(emp_ids) > 1:
            # Multi-resource brand process
            used_offs_in_pair = set()
            for e_id in emp_ids:
                emp = emp_dict.get(e_id, {})
                off = emp.get("default_weekly_off", 6)
                pref = emp.get("preferred_weekly_off", off)
                rule = emp.get("weekly_off_rule", "FIXED")

                if off in used_offs_in_pair and rule == "ROTATIONAL":
                    # Stagger off to another day (e.g., next day) to preserve coverage
                    new_off = (off + 1) % 7
                    assigned_offs[e_id] = new_off
                    used_offs_in_pair.add(new_off)
                    b_id, p_id = bp_key
                    # Record soft preference override
                    for d_obj in month_dates:
                        if d_obj.weekday() == new_off:
                            soft_preference_overrides.append({
                                "employee_id": e_id,
                                "date": d_obj.strftime("%Y-%m-%d"),
                                "brand_id": b_id,
                                "brand_name": brand_dict.get(b_id, {}).get("name", b_id),
                                "process_id": p_id,
                                "preferred_day_name": WEEKDAY_NAMES[pref],
                                "assigned_day_name": WEEKDAY_NAMES[new_off],
                            })
                else:
                    used_offs_in_pair.add(off)

    for emp in employees:
        emp_effective_off[emp["id"]] = assigned_offs.get(emp["id"], emp.get("default_weekly_off", 6))

    # Step 2: Build Base Employee Daily Statuses
    # entries: list of dicts
    entries_list: List[Dict[str, Any]] = []
    emp_status_by_date: Dict[str, Dict[str, str]] = defaultdict(dict)  # date -> emp_id -> status

    for emp in employees:
        e_id = emp["id"]
        eff_off = emp_effective_off[e_id]
        has_365 = emp_has_365_rule.get(e_id, False)

        for d_obj in month_dates:
            d_str = d_obj.strftime("%Y-%m-%d")
            weekday = d_obj.weekday()
            is_ph = d_str in ph_dates

            # Base status resolution
            if (e_id, d_str) in approved_leaves_map:
                lvc = approved_leaves_map[(e_id, d_str)]
                status = lvc.get("type", "PLANNED_LEAVE")
            elif is_ph and not has_365:
                # Employee receives Public Holiday if none of primary brands operate on PH (365_DAYS)
                status = "PUBLIC_HOLIDAY"
            elif weekday == eff_off:
                status = "WEEKLY_OFF"
            else:
                status = "WORKING"

            # Check manual override
            override = manual_overrides_map.get((e_id, d_str))
            is_manual = False
            assigned_brand = None
            assigned_process = None
            notes = None

            if override:
                status = override.get("status", status)
                is_manual = True
                assigned_brand = override.get("assigned_brand_id")
                assigned_process = override.get("assigned_process_id")
                notes = override.get("notes")

            entry = {
                "employee_id": e_id,
                "date": d_str,
                "status": status,
                "assigned_brand_id": assigned_brand,
                "assigned_process_id": assigned_process,
                "is_manual_override": is_manual,
                "notes": notes,
            }
            entries_list.append(entry)
            emp_status_by_date[d_str][e_id] = status

    # Step 3: Evaluate Daily Coverage & Auto-Assign Configured Backups
    coverage_matrix: List[Dict[str, Any]] = []
    # Track assigned backups per date to prevent double-booking: date -> set of emp_ids
    assigned_backups_by_date: Dict[str, Set[str]] = defaultdict(set)

    # Sort rules to evaluate high-priority / peak rules first
    sorted_rules = sorted(brand_process_rules, key=lambda r: (r.get("calendar_type") != "365_DAYS", r["id"]))

    for d_obj in month_dates:
        d_str = d_obj.strftime("%Y-%m-%d")
        is_ph = d_str in ph_dates

        for rule in sorted_rules:
            b_id = rule["brand_id"]
            p_id = rule["process_id"]
            cal_type = rule.get("calendar_type", "365_DAYS")
            base_min = rule.get("min_staffing", 1)
            day_overrides = rule.get("day_min_staffing_overrides", {})
            b_name = brand_dict.get(b_id, {}).get("name", b_id)
            p_code = proc_dict.get(p_id, {}).get("code", p_id)

            is_op = is_operating_day(cal_type, d_obj, is_ph)
            req_staffing = get_required_staffing(cal_type, d_obj, is_ph, base_min, day_overrides)

            if not is_op or req_staffing == 0:
                coverage_matrix.append({
                    "date": d_str,
                    "brand_id": b_id,
                    "brand_name": b_name,
                    "process_id": p_id,
                    "process_code": p_code,
                    "calendar_type": cal_type,
                    "is_operating": False,
                    "required_staffing": 0,
                    "working_count": 0,
                    "status": "NOT_OPERATING",
                    "assigned_employee_ids": [],
                    "backup_employee_ids": [],
                })
                continue

            # Find primary allocated employees who are WORKING on this date
            primaries = primary_allocations_by_bp.get((b_id, p_id), [])
            active_primaries = [
                e_id for e_id in primaries
                if emp_status_by_date[d_str].get(e_id) in ("WORKING", "BACKUP_COVERAGE")
            ]

            backup_ids_assigned: List[str] = []
            if len(active_primaries) >= req_staffing:
                status = "COVERED"
            else:
                # Need backup
                shortfall = req_staffing - len(active_primaries)
                configured_backups = backup_allocations_by_bp.get((b_id, p_id), [])
                for b_emp_id in configured_backups:
                    if shortfall <= 0:
                        break
                    # Must be WORKING and not already assigned as backup on another gap today
                    if (emp_status_by_date[d_str].get(b_emp_id) in ("WORKING", "BACKUP_COVERAGE") and
                            b_emp_id not in assigned_backups_by_date[d_str]):
                        backup_ids_assigned.append(b_emp_id)
                        assigned_backups_by_date[d_str].add(b_emp_id)
                        shortfall -= 1

                        # Update entry status for the backup employee
                        for e_entry in entries_list:
                            if e_entry["employee_id"] == b_emp_id and e_entry["date"] == d_str:
                                if not e_entry.get("is_manual_override"):
                                    e_entry["status"] = "BACKUP_COVERAGE"
                                    e_entry["assigned_brand_id"] = b_id
                                    e_entry["assigned_process_id"] = p_id
                                break

                total_covering = len(active_primaries) + len(backup_ids_assigned)
                if total_covering >= req_staffing:
                    status = "BACKUP_COVERED"
                elif total_covering > 0:
                    status = "UNDERSTAFFED"
                else:
                    status = "UNCOVERED"

            coverage_matrix.append({
                "date": d_str,
                "brand_id": b_id,
                "brand_name": b_name,
                "process_id": p_id,
                "process_code": p_code,
                "calendar_type": cal_type,
                "is_operating": True,
                "required_staffing": req_staffing,
                "working_count": len(active_primaries) + len(backup_ids_assigned),
                "status": status,
                "assigned_employee_ids": active_primaries,
                "backup_employee_ids": backup_ids_assigned,
            })

    return recalculate_coverage_and_validate(
        month_str=month_str,
        entries=entries_list,
        employees=employees,
        brands=brands,
        processes=processes,
        brand_process_rules=brand_process_rules,
        allocations=allocations,
        public_holidays=public_holidays,
        leaves_and_compoffs=leaves_and_compoffs,
        soft_preference_overrides=soft_preference_overrides,
    )


def recalculate_coverage_and_validate(
    month_str: str,
    entries: List[Dict[str, Any]],
    employees: List[Dict[str, Any]],
    brands: List[Dict[str, Any]],
    processes: List[Dict[str, Any]],
    brand_process_rules: List[Dict[str, Any]],
    allocations: List[Dict[str, Any]],
    public_holidays: List[Dict[str, Any]],
    leaves_and_compoffs: List[Dict[str, Any]],
    soft_preference_overrides: Optional[List[Dict[str, Any]]] = None,
    roster_status: str = "DRAFT",
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Pure incremental re-evaluation helper.
    Takes existing roster entries (e.g. after a manual edit, backup assignment, or leave approval),
    evaluates coverage_matrix (respecting BACKUP_COVERAGE entries with assigned_brand_id &
    assigned_process_id as well as WORKING primary employees), runs validate_roster,
    computes KPIs, and returns the MonthlyRosterResponse dict.
    """
    month_dates = get_month_dates(month_str)
    brand_dict = {b["id"]: b for b in brands}
    proc_dict = {p["id"]: p for p in processes}
    ph_dates = {ph["date"] for ph in public_holidays}

    primary_allocations_by_bp: Dict[tuple, List[str]] = defaultdict(list)
    for alc in allocations:
        if alc.get("allocation_type") == "PRIMARY":
            primary_allocations_by_bp[(alc["brand_id"], alc["process_id"])].append(alc["employee_id"])

    emp_status_by_date: Dict[str, Dict[str, str]] = defaultdict(dict)
    assigned_backups_by_bp_date: Dict[tuple, List[str]] = defaultdict(list)

    for entry in entries:
        d_str = entry["date"]
        e_id = entry["employee_id"]
        status = entry.get("status", "WORKING")
        emp_status_by_date[d_str][e_id] = status
        if status == "BACKUP_COVERAGE":
            b_id = entry.get("assigned_brand_id")
            p_id = entry.get("assigned_process_id")
            if b_id and p_id:
                assigned_backups_by_bp_date[(b_id, p_id, d_str)].append(e_id)

    sorted_rules = sorted(
        brand_process_rules,
        key=lambda r: (r.get("calendar_type") != "365_DAYS", r["id"]),
    )

    coverage_matrix: List[Dict[str, Any]] = []
    for d_obj in month_dates:
        d_str = d_obj.strftime("%Y-%m-%d")
        is_ph = d_str in ph_dates

        for rule in sorted_rules:
            b_id = rule["brand_id"]
            p_id = rule["process_id"]
            cal_type = rule.get("calendar_type", "365_DAYS")
            base_min = rule.get("min_staffing", 1)
            day_overrides = rule.get("day_min_staffing_overrides", {})
            b_name = brand_dict.get(b_id, {}).get("name", b_id)
            p_code = proc_dict.get(p_id, {}).get("code", p_id)

            is_op = is_operating_day(cal_type, d_obj, is_ph)
            req_staffing = get_required_staffing(cal_type, d_obj, is_ph, base_min, day_overrides)

            if not is_op or req_staffing == 0:
                coverage_matrix.append({
                    "date": d_str,
                    "brand_id": b_id,
                    "brand_name": b_name,
                    "process_id": p_id,
                    "process_code": p_code,
                    "calendar_type": cal_type,
                    "is_operating": False,
                    "required_staffing": 0,
                    "working_count": 0,
                    "status": "NOT_OPERATING",
                    "assigned_employee_ids": [],
                    "backup_employee_ids": [],
                })
                continue

            assigned_backups = assigned_backups_by_bp_date.get((b_id, p_id, d_str), [])
            assigned_backups_set = set(assigned_backups)

            primaries = primary_allocations_by_bp.get((b_id, p_id), [])
            active_primaries = [
                e_id for e_id in primaries
                if e_id not in assigned_backups_set
                and emp_status_by_date[d_str].get(e_id) in ("WORKING", "BACKUP_COVERAGE")
            ]

            working_count = len(active_primaries) + len(assigned_backups)
            if len(active_primaries) >= req_staffing and not assigned_backups:
                cov_status = "COVERED"
            elif working_count >= req_staffing:
                cov_status = "BACKUP_COVERED" if assigned_backups else "COVERED"
            elif working_count > 0:
                cov_status = "UNDERSTAFFED"
            else:
                cov_status = "UNCOVERED"

            coverage_matrix.append({
                "date": d_str,
                "brand_id": b_id,
                "brand_name": b_name,
                "process_id": p_id,
                "process_code": p_code,
                "calendar_type": cal_type,
                "is_operating": True,
                "required_staffing": req_staffing,
                "working_count": working_count,
                "status": cov_status,
                "assigned_employee_ids": active_primaries,
                "backup_employee_ids": list(assigned_backups),
            })

    conflicts = validate_roster(
        roster_entries=entries,
        coverage_matrix=coverage_matrix,
        employees=employees,
        brands=brands,
        processes=processes,
        allocations=allocations,
        leaves_and_compoffs=leaves_and_compoffs,
        soft_preference_overrides=soft_preference_overrides,
    )

    operating_slots = [c for c in coverage_matrix if c.get("is_operating")]
    covered_or_backup_slots = [
        c for c in operating_slots if c.get("status") in ("COVERED", "BACKUP_COVERED")
    ]
    uncovered_slots = [c for c in operating_slots if c.get("status") == "UNCOVERED"]
    understaffed_slots = [c for c in operating_slots if c.get("status") == "UNDERSTAFFED"]
    hard_conflicts = [c for c in conflicts if c.get("severity") == "HARD"]
    soft_conflicts = [c for c in conflicts if c.get("severity") == "SOFT"]

    coverage_rate = (
        (len(covered_or_backup_slots) / len(operating_slots) * 100.0)
        if operating_slots
        else 100.0
    )

    kpis = {
        "total_employees": len(employees),
        "total_operating_slots": len(operating_slots),
        "covered_slots": len(covered_or_backup_slots),
        "uncovered_slots": len(uncovered_slots),
        "understaffed_slots": len(understaffed_slots),
        "coverage_percentage": round(coverage_rate, 1),
        "hard_conflicts_count": len(hard_conflicts),
        "soft_conflicts_count": len(soft_conflicts),
    }

    return {
        "month": month_str,
        "roster_id": f"ROST-{month_str}",
        "status": roster_status,
        "generated_at": generated_at or datetime.now().isoformat(),
        "kpis": kpis,
        "entries": entries,
        "coverage_matrix": coverage_matrix,
        "conflicts": conflicts,
    }
