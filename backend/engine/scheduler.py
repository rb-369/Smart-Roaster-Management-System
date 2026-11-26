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


def _emp_weekday_demand(
    e_id: str,
    wd: int,
    emp_primary_rules: Dict[str, List[Dict[str, Any]]],
) -> int:
    """Compute single-day staffing demand across an employee's primary brand-process rules."""
    total = 0
    for r in emp_primary_rules.get(e_id, []):
        cal = r.get("calendar_type", "365_DAYS")
        if cal == "MON_SAT_EXCEPT_PH" and wd == 6:
            continue
        base_m = r.get("min_staffing", 1)
        ov = r.get("day_min_staffing_overrides", {})
        total += ov.get(str(wd), base_m)
    return total


def _emp_unbacked_monthly_demand(
    e_id: str,
    wd: int,
    emp_primary_rules: Dict[str, List[Dict[str, Any]]],
    primary_allocations_by_bp: Dict[tuple, List[str]],
    backup_allocations_by_bp: Dict[tuple, List[str]],
    month_dates: List[date],
    ph_dates: Set[str],
) -> int:
    """Compute monthly unbacked staffing shortfall if e_id takes weekday wd off."""
    total = 0
    rules = emp_primary_rules.get(e_id, [])
    if not rules:
        return 0
    for d_obj in month_dates:
        if d_obj.weekday() != wd:
            continue
        is_ph = d_obj.strftime("%Y-%m-%d") in ph_dates
        for r in rules:
            bp_key = (r["brand_id"], r["process_id"])
            req = get_required_staffing(
                r.get("calendar_type", "365_DAYS"),
                d_obj,
                is_ph,
                r.get("min_staffing", 1),
                r.get("day_min_staffing_overrides", {}),
            )
            if req == 0:
                continue
            other_primaries = max(0, len(primary_allocations_by_bp.get(bp_key, [])) - 1)
            backups = len(backup_allocations_by_bp.get(bp_key, []))
            if other_primaries + backups < req:
                total += req - other_primaries - backups
    return total


def _collect_peer_offs(
    e_id: str,
    primary_allocations_by_bp: Dict[tuple, List[str]],
    assigned_offs: Dict[str, int],
    allowed_peers: Optional[Set[str]] = None,
) -> Set[int]:
    """Return assigned off weekdays of peers sharing any multi-resource team with e_id."""
    peer_offs: Set[int] = set()
    for emp_ids in primary_allocations_by_bp.values():
        if e_id in emp_ids and len(emp_ids) > 1:
            for p_id in emp_ids:
                if p_id != e_id and (allowed_peers is None or p_id in allowed_peers):
                    peer_offs.add(assigned_offs[p_id])
    return peer_offs


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

    emp_primary_bp: Dict[str, tuple] = {}
    for bp_key, emp_ids in primary_allocations_by_bp.items():
        for e_id in emp_ids:
            emp_primary_bp.setdefault(e_id, bp_key)

    if strategy == "PREFERENCE_FIRST":
        # Strictly honor every employee's preferred_weekly_off (no staggering)
        for emp in employees:
            e_id = emp["id"]
            pref = emp.get("preferred_weekly_off", emp.get("default_weekly_off", 6))
            for d_obj in month_dates:
                if d_obj.weekday() == pref:
                    emp_weekly_off_dates[e_id].add(d_obj.strftime("%Y-%m-%d"))
    elif strategy == "COVERAGE_FIRST":
        assigned_offs: Dict[str, int] = {
            emp["id"]: emp.get("default_weekly_off", 6) for emp in employees
        }
        # Pick the weekday with minimum total primary demand for each employee,
        # while keeping multi-resource peers staggered on distinct weekdays.
        for emp in employees:
            e_id = emp["id"]
            if not emp_primary_rules.get(e_id):
                continue
            cur_off = assigned_offs[e_id]
            peer_offs = _collect_peer_offs(e_id, primary_allocations_by_bp, assigned_offs)
            assigned_offs[e_id] = min(
                range(7),
                key=lambda wd: (
                    1 if wd in peer_offs else 0,
                    _emp_weekday_demand(e_id, wd, emp_primary_rules),
                    0 if wd == cur_off else 1,
                ),
            )

        for bp_key, emp_ids in primary_allocations_by_bp.items():
            if len(emp_ids) > 1:
                used_offs_in_pair: Set[int] = set()
                for e_id in emp_ids:
                    emp = emp_dict.get(e_id, {})
                    off = assigned_offs.get(e_id, emp.get("default_weekly_off", 6))
                    if off in used_offs_in_pair:
                        new_off = off
                        for offset in range(1, 7):
                            cand = (off + offset) % 7
                            if cand not in used_offs_in_pair:
                                new_off = cand
                                break
                        assigned_offs[e_id] = new_off
                        used_offs_in_pair.add(new_off)
                    else:
                        used_offs_in_pair.add(off)

        for emp in employees:
            e_id = emp["id"]
            pref = emp.get("preferred_weekly_off", emp.get("default_weekly_off", 6))
            bp_key = emp_primary_bp.get(e_id)
            b_id = bp_key[0] if bp_key else None
            p_id = bp_key[1] if bp_key else None
            b_name = brand_dict.get(b_id, {}).get("name", b_id) if b_id else "client"
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
    else:
        # BALANCED: Start from preferred_weekly_off (Pareto middle ground between coverage & preference).
        assigned_offs = {
            emp["id"]: emp.get("preferred_weekly_off", emp.get("default_weekly_off", 6))
            for emp in employees
        }

        # 1. Demand-relief pass: only override preferred_weekly_off when another weekday has
        # strictly lower single-day demand without colliding, or default_weekly_off strictly
        # reduces monthly unbacked staffing gaps (e.g. non-operating Sundays / holiday alignment).
        for emp in employees:
            e_id = emp["id"]
            if not emp_primary_rules.get(e_id):
                continue
            pref = assigned_offs[e_id]
            default_off = emp.get("default_weekly_off", 6)
            peer_offs = _collect_peer_offs(e_id, primary_allocations_by_bp, assigned_offs)
            pref_daily = _emp_weekday_demand(e_id, pref, emp_primary_rules)
            best_daily_wd = min(
                range(7),
                key=lambda wd: (
                    1 if (wd in peer_offs and wd != pref) else 0,
                    _emp_weekday_demand(e_id, wd, emp_primary_rules),
                    0 if wd == pref else 1,
                    0 if wd == default_off else 1,
                    wd,
                ),
            )
            if (
                best_daily_wd not in peer_offs
                and _emp_weekday_demand(e_id, best_daily_wd, emp_primary_rules) < pref_daily
            ):
                assigned_offs[e_id] = best_daily_wd
            elif default_off != pref and default_off not in peer_offs:
                pref_unbacked = _emp_unbacked_monthly_demand(
                    e_id, pref, emp_primary_rules, primary_allocations_by_bp,
                    backup_allocations_by_bp, month_dates, ph_dates,
                )
                def_unbacked = _emp_unbacked_monthly_demand(
                    e_id, default_off, emp_primary_rules, primary_allocations_by_bp,
                    backup_allocations_by_bp, month_dates, ph_dates,
                )
                if def_unbacked < pref_unbacked:
                    assigned_offs[e_id] = default_off

        # 2. Multi-resource peer staggering: only stagger colliding ROTATIONAL peers onto
        # the lowest-demand non-colliding weekday, keeping FIXED peers untouched.
        locked_peers: Set[str] = {
            emp["id"] for emp in employees if emp.get("weekly_off_rule", "FIXED") != "ROTATIONAL"
        }
        staggered_multi_emps: Set[str] = set()
        for emp in employees:
            e_id = emp["id"]
            if emp.get("weekly_off_rule", "FIXED") != "ROTATIONAL":
                continue
            in_multi_team = any(
                e_id in emp_ids and len(emp_ids) > 1
                for emp_ids in primary_allocations_by_bp.values()
            )
            if not in_multi_team:
                locked_peers.add(e_id)
                continue

            peer_offs = _collect_peer_offs(
                e_id, primary_allocations_by_bp, assigned_offs, allowed_peers=locked_peers
            )
            if assigned_offs[e_id] in peer_offs:
                pref = emp.get("preferred_weekly_off", emp.get("default_weekly_off", 6))
                default_off = emp.get("default_weekly_off", 6)
                candidates = [wd for wd in range(7) if wd not in peer_offs] or list(range(7))
                assigned_offs[e_id] = min(
                    candidates,
                    key=lambda wd: (
                        _emp_weekday_demand(e_id, wd, emp_primary_rules),
                        0 if wd == pref else 1,
                        0 if wd == default_off else 1,
                        wd,
                    ),
                )
                staggered_multi_emps.add(e_id)
            locked_peers.add(e_id)

        # 3. Build monthly weekly-off dates; non-staggered ROTATIONAL employees whose
        # default_weekly_off differs from assigned_offs[e_id] open Week 1 on default_weekly_off
        # and transition smoothly to assigned_offs[e_id] (max gap <= 6 days, 0 stretch violations).
        for emp in employees:
            e_id = emp["id"]
            pref = emp.get("preferred_weekly_off", emp.get("default_weekly_off", 6))
            default_off = emp.get("default_weekly_off", 6)
            eff_off = assigned_offs[e_id]
            rule = emp.get("weekly_off_rule", "FIXED")
            has_365 = emp_has_365_rule.get(e_id, False)

            bp_key = emp_primary_bp.get(e_id)
            b_id = bp_key[0] if bp_key else None
            p_id = bp_key[1] if bp_key else None
            b_name = brand_dict.get(b_id, {}).get("name", b_id) if b_id else "client"

            first_default_date: Optional[date] = None
            if rule == "ROTATIONAL" and default_off != eff_off and e_id not in staggered_multi_emps:
                peer_offs = _collect_peer_offs(e_id, primary_allocations_by_bp, assigned_offs)
                if default_off not in peer_offs:
                    first_default_date = next(
                        (d_obj for d_obj in month_dates[:7] if d_obj.weekday() == default_off),
                        None,
                    )

            for d_obj in month_dates:
                d_str = d_obj.strftime("%Y-%m-%d")
                if first_default_date is not None:
                    if d_obj == first_default_date:
                        assigned_wd = default_off
                    elif d_obj > first_default_date and d_obj.weekday() == eff_off:
                        assigned_wd = eff_off
                    else:
                        continue
                elif d_obj.weekday() == eff_off:
                    assigned_wd = eff_off
                else:
                    continue

                emp_weekly_off_dates[e_id].add(d_str)
                if assigned_wd != pref and not (d_str in ph_dates and not has_365):
                    soft_preference_overrides.append({
                        "employee_id": e_id,
                        "date": d_str,
                        "brand_id": b_id,
                        "brand_name": b_name,
                        "process_id": p_id,
                        "preferred_day_name": WEEKDAY_NAMES[pref],
                        "assigned_day_name": WEEKDAY_NAMES[assigned_wd],
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


def _derive_soft_preference_overrides(
    entries: List[Dict[str, Any]],
    employees: List[Dict[str, Any]],
    brands: List[Dict[str, Any]],
    allocations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Derive PREFERENCE_VIOLATED soft conflicts from current roster entries.
    For every WEEKLY_OFF entry that falls on a day != employee's preferred_weekly_off,
    emit a soft preference override record so the validator can flag it.
    """
    emp_dict = {e["id"]: e for e in employees}
    brand_dict = {b["id"]: b for b in brands}

    # Map emp -> first primary brand
    emp_primary_bp: Dict[str, tuple] = {}
    for alc in allocations:
        if alc.get("allocation_type") == "PRIMARY":
            emp_primary_bp.setdefault(alc["employee_id"], (alc["brand_id"], alc["process_id"]))

    overrides: List[Dict[str, Any]] = []
    for entry in entries:
        if entry.get("status") != "WEEKLY_OFF":
            continue
        e_id = entry["employee_id"]
        emp = emp_dict.get(e_id)
        if not emp:
            continue
        pref = emp.get("preferred_weekly_off", emp.get("default_weekly_off", 6))
        d_str = entry["date"]
        d_obj = datetime.strptime(d_str, "%Y-%m-%d").date()
        actual_wd = d_obj.weekday()
        if actual_wd != pref:
            bp_key = emp_primary_bp.get(e_id)
            b_id = bp_key[0] if bp_key else None
            p_id = bp_key[1] if bp_key else None
            b_name = brand_dict.get(b_id, {}).get("name", b_id) if b_id else "client"
            overrides.append({
                "employee_id": e_id,
                "date": d_str,
                "brand_id": b_id,
                "brand_name": b_name,
                "process_id": p_id,
                "preferred_day_name": WEEKDAY_NAMES[pref],
                "assigned_day_name": WEEKDAY_NAMES[actual_wd],
            })
    return overrides


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
    # If soft_preference_overrides not provided (e.g. after manual edit / backup assign),
    # derive them from the current entries so PREFERENCE_VIOLATED soft conflicts are preserved.
    if soft_preference_overrides is None:
        soft_preference_overrides = _derive_soft_preference_overrides(
            entries, employees, brands, allocations
        )

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


def _conflict_key(conflict: Dict[str, Any]) -> tuple:
    """Return the canonical identity tuple used to diff conflicts before/after a change."""
    return (
        conflict.get("date"),
        conflict.get("conflict_type"),
        conflict.get("brand_id"),
        conflict.get("process_id"),
        conflict.get("employee_id"),
    )


def preview_leave_impact(
    month_str: str,
    entries: List[Dict[str, Any]],
    employee_id: str,
    start_date: str,
    end_date: str,
    leave_type: str,
    employees: List[Dict[str, Any]],
    brands: List[Dict[str, Any]],
    processes: List[Dict[str, Any]],
    brand_process_rules: List[Dict[str, Any]],
    allocations: List[Dict[str, Any]],
    public_holidays: List[Dict[str, Any]],
    leaves_and_compoffs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Pure dry-run simulation of approving a leave/comp-off on an existing monthly roster.
    Clones entries and leaves in memory without mutating any caller inputs, compares
    coverage and HARD conflicts before vs. after, and returns affected entities and
    ranked backup suggestions for every newly introduced hard conflict.
    """
    before_res = recalculate_coverage_and_validate(
        month_str=month_str,
        entries=entries,
        employees=employees,
        brands=brands,
        processes=processes,
        brand_process_rules=brand_process_rules,
        allocations=allocations,
        public_holidays=public_holidays,
        leaves_and_compoffs=leaves_and_compoffs,
    )

    cloned_entries: List[Dict[str, Any]] = []
    for entry in entries:
        item = dict(entry)
        if item["employee_id"] == employee_id and start_date <= item["date"] <= end_date:
            item["status"] = leave_type
            item["assigned_brand_id"] = None
            item["assigned_process_id"] = None
            item["is_manual_override"] = False
        cloned_entries.append(item)

    cloned_leaves = [dict(lvc) for lvc in leaves_and_compoffs]
    cloned_leaves.append({
        "id": "__PREVIEW__",
        "employee_id": employee_id,
        "start_date": start_date,
        "end_date": end_date,
        "type": leave_type,
        "status": "APPROVED",
    })

    after_res = recalculate_coverage_and_validate(
        month_str=month_str,
        entries=cloned_entries,
        employees=employees,
        brands=brands,
        processes=processes,
        brand_process_rules=brand_process_rules,
        allocations=allocations,
        public_holidays=public_holidays,
        leaves_and_compoffs=cloned_leaves,
    )

    before_hard_keys = {
        _conflict_key(c)
        for c in before_res["conflicts"]
        if c.get("severity") == "HARD"
    }
    new_hard_conflicts = [
        c
        for c in after_res["conflicts"]
        if c.get("severity") == "HARD" and _conflict_key(c) not in before_hard_keys
    ]

    brand_dict = {b["id"]: b for b in brands}
    proc_dict = {p["id"]: p for p in processes}

    affected_dates = sorted({c["date"] for c in new_hard_conflicts if c.get("date")})

    affected_brands_map: Dict[str, str] = {}
    affected_processes_set: Set[str] = set()
    for conf in new_hard_conflicts:
        b_id = conf.get("brand_id")
        if b_id and b_id not in affected_brands_map:
            affected_brands_map[b_id] = (
                brand_dict.get(b_id, {}).get("name")
                or conf.get("brand_name")
                or b_id
            )
        p_id = conf.get("process_id")
        if p_id:
            proc_label = (
                proc_dict.get(p_id, {}).get("code")
                or proc_dict.get(p_id, {}).get("name")
                or conf.get("process_name")
                or p_id
            )
            affected_processes_set.add(proc_label)

    affected_brands = [
        {"brand_id": b_id, "brand_name": b_name}
        for b_id, b_name in sorted(affected_brands_map.items(), key=lambda item: item[0])
    ]

    return {
        "hard_conflicts_before": before_res["kpis"]["hard_conflicts_count"],
        "hard_conflicts_after": after_res["kpis"]["hard_conflicts_count"],
        "new_hard_conflicts_count": len(new_hard_conflicts),
        "coverage_before": float(before_res["kpis"]["coverage_percentage"]),
        "coverage_after": float(after_res["kpis"]["coverage_percentage"]),
        "affected_dates": affected_dates,
        "affected_brands": affected_brands,
        "affected_processes": sorted(affected_processes_set),
        "new_conflicts": new_hard_conflicts,
    }
