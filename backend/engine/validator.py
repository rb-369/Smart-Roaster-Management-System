"""
Conflict Detector and Roster Validator.
PURE DETERMINISTIC LOGIC - NO FASTAPI OR DATABASE CALLS.
"""
from typing import List, Dict, Any, Set
from collections import defaultdict
from datetime import datetime, timedelta
from .recommender import recommend_backups


def validate_roster(
    roster_entries: List[Dict[str, Any]],
    coverage_matrix: List[Dict[str, Any]],
    employees: List[Dict[str, Any]],
    brands: List[Dict[str, Any]],
    processes: List[Dict[str, Any]],
    allocations: List[Dict[str, Any]],
    leaves_and_compoffs: List[Dict[str, Any]],
    soft_preference_overrides: List[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    """
    Runs the 6 mandatory validation passes across the generated roster and daily coverage:
    1. UNCOVERED_BRAND_PROCESS (HARD)
    2. INSUFFICIENT_STAFFING (HARD)
    3. MULTI_BRAND_CASCADE (HARD)
    4. LEAVE_OR_OFF_VIOLATION (HARD)
    5. SHIFT_OR_OVERLOAD_CONFLICT (HARD)
    6. PREFERENCE_VIOLATED (SOFT)
    """
    conflicts: List[Dict[str, Any]] = []

    emp_dict = {e["id"]: e for e in employees}
    brand_dict = {b["id"]: b for b in brands}
    proc_dict = {p["id"]: p for p in processes}

    # Group entries by employee and date
    entries_by_emp_date: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    entries_by_date_emp: Dict[str, Dict[str, str]] = defaultdict(dict)
    dates_seen = set()

    for entry in roster_entries:
        e_id = entry["employee_id"]
        d = entry["date"]
        dates_seen.add(d)
        entries_by_emp_date[e_id][d] = entry
        entries_by_date_emp[d][e_id] = entry.get("status", "WORKING")

    # Map primary allocations: emp_id -> set of (brand_id, process_id)
    emp_primary_allocations: Dict[str, Set[tuple]] = defaultdict(set)
    for alc in allocations:
        if alc.get("allocation_type") == "PRIMARY":
            emp_primary_allocations[alc["employee_id"]].add((alc["brand_id"], alc["process_id"]))

    # 1 & 2: Evaluate Coverage Shortfalls (UNCOVERED_BRAND_PROCESS & INSUFFICIENT_STAFFING)
    # Track gaps by (date, brand_id) to detect multi-brand cascade later
    gaps_by_date_brand: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))

    for cov in coverage_matrix:
        d = cov["date"]
        b_id = cov["brand_id"]
        p_id = cov["process_id"]
        b_name = cov.get("brand_name", brand_dict.get(b_id, {}).get("name", b_id))
        p_name = cov.get("process_code", proc_dict.get(p_id, {}).get("code", p_id))
        is_op = cov.get("is_operating", True)
        req = cov.get("required_staffing", 0)
        actual = cov.get("working_count", 0)
        status = cov.get("status")

        if not is_op or req == 0:
            continue

        if actual == 0:
            b_info = brand_dict.get(b_id, {})
            b_pod = b_info.get("pod_id", "")
            resolutions = recommend_backups(
                brand_id=b_id,
                process_id=p_id,
                date_str=d,
                brand_pod_id=b_pod,
                employees=employees,
                employee_statuses=entries_by_date_emp[d],
                allocations=allocations,
            )
            conflict = {
                "date": d,
                "severity": "HARD",
                "conflict_type": "UNCOVERED_BRAND_PROCESS",
                "brand_id": b_id,
                "brand_name": b_name,
                "process_id": p_id,
                "process_name": p_name,
                "employee_id": None,
                "message": f"Brand {b_name} requires {req} staff for {p_name} on {d}, but 0 employees are covering (UNCOVERED).",
                "suggested_resolutions": resolutions,
                "resolved": False,
            }
            conflicts.append(conflict)
            gaps_by_date_brand[d][b_id].append(cov)

        elif 0 < actual < req:
            b_info = brand_dict.get(b_id, {})
            b_pod = b_info.get("pod_id", "")
            resolutions = recommend_backups(
                brand_id=b_id,
                process_id=p_id,
                date_str=d,
                brand_pod_id=b_pod,
                employees=employees,
                employee_statuses=entries_by_date_emp[d],
                allocations=allocations,
            )
            shortfall = req - actual
            conflict = {
                "date": d,
                "severity": "HARD",
                "conflict_type": "INSUFFICIENT_STAFFING",
                "brand_id": b_id,
                "brand_name": b_name,
                "process_id": p_id,
                "process_name": p_name,
                "employee_id": None,
                "message": f"Brand {b_name} requires {req} staff for {p_name} on {d}, but only {actual} is covering ({shortfall} short).",
                "suggested_resolutions": resolutions,
                "resolved": False,
            }
            conflicts.append(conflict)
            gaps_by_date_brand[d][b_id].append(cov)

    # 3: MULTI_BRAND_CASCADE (HARD)
    # Check if an employee's absence on a date causes gaps on >= 2 distinct brands
    for d, b_gaps in gaps_by_date_brand.items():
        if len(b_gaps) >= 2:
            # Check which absent employees are primary on >= 2 of these gap brands
            for emp in employees:
                e_id = emp["id"]
                status = entries_by_date_emp[d].get(e_id, "WORKING")
                if status in ("PLANNED_LEAVE", "COMP_OFF", "WEEKLY_OFF"):
                    # Brands for which this employee is primary
                    primary_brands = {b for (b, p) in emp_primary_allocations.get(e_id, set())}
                    impacted_brands = primary_brands.intersection(b_gaps.keys())
                    if len(impacted_brands) >= 2:
                        brand_names = [brand_dict.get(b, {}).get("name", b) for b in impacted_brands]
                        conflicts.append({
                            "date": d,
                            "severity": "HARD",
                            "conflict_type": "MULTI_BRAND_CASCADE",
                            "brand_id": list(impacted_brands)[0],
                            "brand_name": ", ".join(brand_names),
                            "process_id": None,
                            "process_name": "Multiple Processes",
                            "employee_id": e_id,
                            "employee_name": emp.get("name", e_id),
                            "message": f"Cascading gap: Employee {emp.get('name', e_id)} ({e_id}) is on {status} on {d}, causing simultaneous gaps across {len(impacted_brands)} brands ({', '.join(brand_names)}).",
                            "suggested_resolutions": [],
                            "resolved": False,
                        })

    # 4: LEAVE_OR_OFF_VIOLATION (HARD)
    # Check 4a: Employee scheduled as WORKING on an approved leave or comp-off
    approved_leaves = [l for l in leaves_and_compoffs if l.get("status") == "APPROVED"]
    for lvc in approved_leaves:
        e_id = lvc["employee_id"]
        start_d = datetime.strptime(lvc["start_date"], "%Y-%m-%d").date()
        end_d = datetime.strptime(lvc["end_date"], "%Y-%m-%d").date()
        cur_d = start_d
        while cur_d <= end_d:
            cur_d_str = cur_d.strftime("%Y-%m-%d")
            entry = entries_by_emp_date.get(e_id, {}).get(cur_d_str)
            if entry and entry.get("status") in ("WORKING", "BACKUP_COVERAGE") and entry.get("is_manual_override"):
                emp = emp_dict.get(e_id, {})
                conflicts.append({
                    "date": cur_d_str,
                    "severity": "HARD",
                    "conflict_type": "LEAVE_OR_OFF_VIOLATION",
                    "brand_id": None,
                    "process_id": None,
                    "employee_id": e_id,
                    "employee_name": emp.get("name", e_id),
                    "message": f"Leave violation: Employee {emp.get('name', e_id)} is marked as {entry['status']} during approved {lvc['type']} ({cur_d_str}).",
                    "suggested_resolutions": [],
                    "resolved": False,
                })
            cur_d += timedelta(days=1)

    # Check 4b: Employee has 0 weekly offs in any rolling 7-day period
    sorted_dates = sorted(list(dates_seen))
    if len(sorted_dates) >= 7:
        for emp in employees:
            e_id = emp["id"]
            for i in range(len(sorted_dates) - 6):
                window = sorted_dates[i:i+7]
                statuses = [entries_by_emp_date.get(e_id, {}).get(w_date, {}).get("status") for w_date in window]
                weekly_off_count = statuses.count("WEEKLY_OFF")
                # If worked 7 straight days with 0 weekly off (and not on leave all week)
                working_count = statuses.count("WORKING") + statuses.count("BACKUP_COVERAGE")
                if working_count == 7 and weekly_off_count == 0:
                    conflicts.append({
                        "date": window[-1],
                        "severity": "HARD",
                        "conflict_type": "LEAVE_OR_OFF_VIOLATION",
                        "brand_id": None,
                        "process_id": None,
                        "employee_id": e_id,
                        "employee_name": emp.get("name", e_id),
                        "message": f"Labor rule violation: Employee {emp.get('name', e_id)} has 0 weekly offs in a 7-day stretch ({window[0]} to {window[-1]}).",
                        "suggested_resolutions": [],
                        "resolved": False,
                    })
                    break  # Emit once per stretch to avoid spamming

    # 5: SHIFT_OR_OVERLOAD_CONFLICT (HARD)
    # Check if an employee is assigned to > 3 brands simultaneously on the same date
    emp_brand_counts_by_date: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
    for entry in roster_entries:
        if entry.get("status") in ("WORKING", "BACKUP_COVERAGE"):
            e_id = entry["employee_id"]
            d = entry["date"]
            # Primary brands
            for (b_id, _) in emp_primary_allocations.get(e_id, set()):
                emp_brand_counts_by_date[d][e_id].add(b_id)
            if entry.get("assigned_brand_id"):
                emp_brand_counts_by_date[d][e_id].add(entry["assigned_brand_id"])

    for d, emp_brands in emp_brand_counts_by_date.items():
        for e_id, b_set in emp_brands.items():
            if len(b_set) > 3:
                emp = emp_dict.get(e_id, {})
                conflicts.append({
                    "date": d,
                    "severity": "HARD",
                    "conflict_type": "SHIFT_OR_OVERLOAD_CONFLICT",
                    "brand_id": None,
                    "process_id": None,
                    "employee_id": e_id,
                    "employee_name": emp.get("name", e_id),
                    "message": f"Overload conflict: Employee {emp.get('name', e_id)} is scheduled across {len(b_set)} brands on {d} (limit is 3).",
                    "suggested_resolutions": [],
                    "resolved": False,
                })

    # 6: PREFERENCE_VIOLATED (SOFT)
    if soft_preference_overrides:
        for pref in soft_preference_overrides:
            e_id = pref["employee_id"]
            emp = emp_dict.get(e_id, {})
            conflicts.append({
                "date": pref["date"],
                "severity": "SOFT",
                "conflict_type": "PREFERENCE_VIOLATED",
                "brand_id": pref.get("brand_id"),
                "process_id": pref.get("process_id"),
                "employee_id": e_id,
                "employee_name": emp.get("name", e_id),
                "message": f"Soft preference overridden: Employee {emp.get('name', e_id)}'s preferred weekly off ({pref.get('preferred_day_name')}) was moved to {pref.get('assigned_day_name')} to maintain client coverage for {pref.get('brand_name', 'client')}.",
                "suggested_resolutions": [],
                "resolved": False,
            })

    return conflicts
