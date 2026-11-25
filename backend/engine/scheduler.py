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
    strategy: str = "BALANCED",
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

    # Weekly off calculation and staggering based on strategy
    if strategy not in ("COVERAGE_FIRST", "PREFERENCE_FIRST", "BALANCED"):
        raise ValueError(f"Unsupported scheduling strategy: {strategy}")

    soft_preference_overrides: List[Dict[str, Any]] = []
    # Map (emp_id, date_str) -> bool indicating if date_str is weekly off for emp_id
    emp_weekly_off_dates: Dict[str, Set[str]] = defaultdict(set)

    if strategy == "PREFERENCE_FIRST":
        # Strictly honor every employee's preferred_weekly_off (no staggering)
        for emp in employees:
            e_id = emp["id"]
            pref = emp.get("preferred_weekly_off", emp.get("default_weekly_off", 6))
            for d_obj in month_dates:
                if d_obj.weekday() == pref:
                    emp_weekly_off_dates[e_id].add(d_obj.strftime("%Y-%m-%d"))
    else:
        # BALANCED or COVERAGE_FIRST
        assigned_offs: Dict[str, int] = {
            emp["id"]: emp.get("default_weekly_off", 6) for emp in employees
        }
        if strategy == "COVERAGE_FIRST":
            # Pick the weekday with minimum total primary demand for each employee,
            # while keeping multi-resource peers staggered on distinct weekdays.
            def _emp_weekday_demand(e_id: str, wd: int) -> int:
                total = 0
                for r in emp_primary_rules.get(e_id, []):
                    cal = r.get("calendar_type", "365_DAYS")
                    if cal == "MON_SAT_EXCEPT_PH" and wd == 6:
                        continue
                    base_m = r.get("min_staffing", 1)
                    ov = r.get("day_min_staffing_overrides", {})
                    total += ov.get(str(wd), base_m)
                return total

            for emp in employees:
                e_id = emp["id"]
                rules = emp_primary_rules.get(e_id, [])
                if not rules:
                    continue
                cur_off = assigned_offs[e_id]
                # Collect peer offs across all multi-resource teams this employee is in
                peer_offs: Set[int] = set()
                for bp_key, emp_ids in primary_allocations_by_bp.items():
                    if e_id in emp_ids and len(emp_ids) > 1:
                        for p_id in emp_ids:
                            if p_id != e_id:
                                peer_offs.add(assigned_offs[p_id])

                # Rank weekdays by: (collides with peer, total demand, wd != cur_off)
                best_wd = min(
                    range(7),
                    key=lambda wd: (
                        1 if wd in peer_offs else 0,
                        _emp_weekday_demand(e_id, wd),
                        0 if wd == cur_off else 1,
                    ),
                )
                assigned_offs[e_id] = best_wd
        # Track rotational employees in multi-resource teams for Sunday fairness rotation
        rotational_info: Dict[str, Dict[str, Any]] = {}
        # Track primary brand_process for preference override reporting
        emp_primary_bp: Dict[str, tuple] = {}
        for bp_key, emp_ids in primary_allocations_by_bp.items():
            for e_id in emp_ids:
                emp_primary_bp.setdefault(e_id, bp_key)

        for bp_key, emp_ids in primary_allocations_by_bp.items():
            if len(emp_ids) > 1:
                used_offs_in_pair: Set[int] = set()
                fixed_offs_in_pair: Set[int] = set()
                for e_id in emp_ids:
                    emp = emp_dict.get(e_id, {})
                    if emp.get("weekly_off_rule", "FIXED") != "ROTATIONAL" and strategy == "BALANCED":
                        fixed_offs_in_pair.add(emp.get("default_weekly_off", 6))

                for e_id in emp_ids:
                    emp = emp_dict.get(e_id, {})
                    off = assigned_offs.get(e_id, emp.get("default_weekly_off", 6))
                    rule = emp.get("weekly_off_rule", "FIXED")
                    should_stagger = (
                        off in used_offs_in_pair
                        and (rule == "ROTATIONAL" or strategy == "COVERAGE_FIRST")
                    )
                    if should_stagger:
                        new_off = off
                        for offset in range(1, 7):
                            cand = (off + offset) % 7
                            if cand not in used_offs_in_pair:
                                new_off = cand
                                break
                        assigned_offs[e_id] = new_off
                        used_offs_in_pair.add(new_off)
                        if strategy == "BALANCED" and rule == "ROTATIONAL":
                            rotational_info[e_id] = {
                                "start_off": new_off,
                                "blocked": set(fixed_offs_in_pair),
                                "bp_key": bp_key,
                            }
                    else:
                        used_offs_in_pair.add(off)
                        if strategy == "BALANCED" and rule == "ROTATIONAL":
                            rotational_info[e_id] = {
                                "start_off": off,
                                "blocked": set(fixed_offs_in_pair),
                                "bp_key": bp_key,
                            }

        # (COVERAGE_FIRST demand-minimizing pass already ran above)

        for emp in employees:
            e_id = emp["id"]
            pref = emp.get("preferred_weekly_off", emp.get("default_weekly_off", 6))
            bp_key = emp_primary_bp.get(e_id)
            b_id = bp_key[0] if bp_key else None
            p_id = bp_key[1] if bp_key else None
            b_name = brand_dict.get(b_id, {}).get("name", b_id) if b_id else "client"

            if strategy == "BALANCED" and e_id in rotational_info:
                info = rotational_info[e_id]
                cur_off = info["start_off"]
                blocked = info["blocked"]
                # Step backward by 1 day per 7-day block to rotate Sunday fairness without 7-day stretch violations
                prev_week_idx = -1
                for d_obj in month_dates:
                    week_idx = (d_obj.day - 1) // 7
                    if week_idx != prev_week_idx:
                        if prev_week_idx != -1:
                            cand = (cur_off - 1) % 7
                            for _ in range(7):
                                if cand not in blocked:
                                    break
                                cand = (cand - 1) % 7
                            cur_off = cand
                        prev_week_idx = week_idx
                    if d_obj.weekday() == cur_off:
                        d_str = d_obj.strftime("%Y-%m-%d")
                        emp_weekly_off_dates[e_id].add(d_str)
                        if cur_off != pref:
                            soft_preference_overrides.append({
                                "employee_id": e_id,
                                "date": d_str,
                                "brand_id": b_id,
                                "brand_name": b_name,
                                "process_id": p_id,
                                "preferred_day_name": WEEKDAY_NAMES[pref],
                                "assigned_day_name": WEEKDAY_NAMES[cur_off],
                            })
            else:
                eff_off = assigned_offs[e_id]
                for d_obj in month_dates:
                    if d_obj.weekday() == eff_off:
                        d_str = d_obj.strftime("%Y-%m-%d")
                        emp_weekly_off_dates[e_id].add(d_str)
                        if eff_off != pref:
                            soft_preference_overrides.append({
                                "employee_id": e_id,
                                "date": d_str,
                                "brand_id": b_id,
                                "brand_name": b_name,
                                "process_id": p_id,
                                "preferred_day_name": WEEKDAY_NAMES[pref],
                                "assigned_day_name": WEEKDAY_NAMES[eff_off],
                            })

    # Step 2: Build Base Employee Daily Statuses
    # entries: list of dicts
    entries_list: List[Dict[str, Any]] = []
    emp_status_by_date: Dict[str, Dict[str, str]] = defaultdict(dict)  # date -> emp_id -> status

    for emp in employees:
        e_id = emp["id"]
        off_dates = emp_weekly_off_dates[e_id]
        has_365 = emp_has_365_rule.get(e_id, False)

        for d_obj in month_dates:
            d_str = d_obj.strftime("%Y-%m-%d")
            is_ph = d_str in ph_dates

            # Base status resolution
            if (e_id, d_str) in approved_leaves_map:
                lvc = approved_leaves_map[(e_id, d_str)]
                status = lvc.get("type", "PLANNED_LEAVE")
            elif is_ph and not has_365:
                # Employee receives Public Holiday if none of primary brands operate on PH (365_DAYS)
                status = "PUBLIC_HOLIDAY"
            elif d_str in off_dates:
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

    # Compute per-employee fairness stats
    emp_stats: Dict[str, Dict[str, Any]] = {}
    for emp in employees:
        e_id = emp["id"]
        emp_stats[e_id] = {
            "employee_id": e_id,
            "name": emp.get("name", e_id),
            "working_days": 0,
            "weekly_offs": 0,
            "sunday_offs": 0,
            "leaves": 0,
            "backup_days": 0,
        }
    for entry in entries:
        e_id = entry["employee_id"]
        if e_id not in emp_stats:
            continue
        st = entry.get("status")
        if st == "WORKING":
            emp_stats[e_id]["working_days"] += 1
        elif st == "BACKUP_COVERAGE":
            emp_stats[e_id]["working_days"] += 1
            emp_stats[e_id]["backup_days"] += 1
        elif st == "WEEKLY_OFF":
            emp_stats[e_id]["weekly_offs"] += 1
            d_obj = datetime.strptime(entry["date"], "%Y-%m-%d").date()
            if d_obj.weekday() == 6:
                emp_stats[e_id]["sunday_offs"] += 1
        elif st in ("PLANNED_LEAVE", "COMP_OFF"):
            emp_stats[e_id]["leaves"] += 1

    sunday_offs_list = [s["sunday_offs"] for s in emp_stats.values()]
    fairness_summary = {
        "min_sunday_offs": min(sunday_offs_list) if sunday_offs_list else 0,
        "max_sunday_offs": max(sunday_offs_list) if sunday_offs_list else 0,
        "avg_working_days": round(
            sum(s["working_days"] for s in emp_stats.values()) / len(emp_stats), 1
        ) if emp_stats else 0.0,
        "per_employee": list(emp_stats.values()),
    }

    kpis = {
        "total_employees": len(employees),
        "total_operating_slots": len(operating_slots),
        "covered_slots": len(covered_or_backup_slots),
        "uncovered_slots": len(uncovered_slots),
        "understaffed_slots": len(understaffed_slots),
        "coverage_percentage": round(coverage_rate, 1),
        "hard_conflicts_count": len(hard_conflicts),
        "soft_conflicts_count": len(soft_conflicts),
        "fairness_summary": fairness_summary,
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
