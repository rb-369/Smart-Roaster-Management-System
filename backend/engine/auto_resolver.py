"""
Deterministic 1-Click Batch Auto-Resolver Engine.
PURE DETERMINISTIC LOGIC - NO FASTAPI OR DATABASE CALLS.
"""
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from .scheduler import recalculate_coverage_and_validate


def _build_structural_gaps_summary(
    conflicts: List[Dict[str, Any]],
    min_score: int,
) -> str:
    """Summarize remaining unresolved HARD conflicts after batch auto-resolution."""
    remaining_hard = [
        c
        for c in conflicts
        if c.get("severity") == "HARD" and not c.get("resolved", False)
    ]
    if not remaining_hard:
        return "All hard conflicts resolved; 0 structural gaps remaining."

    grouped: Counter[Tuple[str, str]] = Counter()
    for conf in remaining_hard:
        label_primary = conf.get("brand_name") or conf.get("brand_id") or conf.get("employee_name") or conf.get("employee_id") or "Unknown"
        label_secondary = conf.get("process_name") or conf.get("process_id") or conf.get("conflict_type", "GAP")
        grouped[(label_primary, label_secondary)] += 1

    sorted_groups = sorted(grouped.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
    top_parts = [
        f"{primary} ({secondary}): {cnt}d"
        for (primary, secondary), cnt in sorted_groups[:5]
    ]
    extra = len(sorted_groups) - len(top_parts)
    suffix = f" (+{extra} more)" if extra > 0 else ""

    return (
        f"{len(remaining_hard)} structural hard conflict(s) remain without eligible "
        f"score>={min_score} backup or due to pod capacity limits: "
        + ", ".join(top_parts)
        + suffix
        + "."
    )


def auto_resolve_gaps(
    month_str: str,
    entries: List[Dict[str, Any]],
    employees: List[Dict[str, Any]],
    brands: List[Dict[str, Any]],
    processes: List[Dict[str, Any]],
    brand_process_rules: List[Dict[str, Any]],
    allocations: List[Dict[str, Any]],
    public_holidays: List[Dict[str, Any]],
    leaves_and_compoffs: List[Dict[str, Any]],
    min_score: int = 70,
    roster_status: str = "DRAFT",
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Deterministically fill eligible HARD coverage conflicts with ranked backups
    (score >= min_score) while enforcing max 1 backup assignment per employee per day.
    """
    working_entries = [dict(e) for e in entries]

    initial_result = recalculate_coverage_and_validate(
        month_str=month_str,
        entries=working_entries,
        employees=employees,
        brands=brands,
        processes=processes,
        brand_process_rules=brand_process_rules,
        allocations=allocations,
        public_holidays=public_holidays,
        leaves_and_compoffs=leaves_and_compoffs,
        roster_status=roster_status,
        generated_at=generated_at,
    )
    coverage_before = float(initial_result["kpis"]["coverage_percentage"])
    hard_before = int(initial_result["kpis"]["hard_conflicts_count"])

    assigned_backups_by_date: Dict[str, Set[str]] = defaultdict(set)
    entry_by_emp_date: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for entry in working_entries:
        emp_id = entry["employee_id"]
        d_str = entry["date"]
        entry_by_emp_date[(emp_id, d_str)] = entry
        if entry.get("status") == "BACKUP_COVERAGE":
            assigned_backups_by_date[d_str].add(emp_id)

    emp_primary_brands: Dict[str, Set[str]] = defaultdict(set)
    for alc in allocations:
        if alc.get("allocation_type") == "PRIMARY":
            emp_primary_brands[alc["employee_id"]].add(alc["brand_id"])

    coverage_conflicts = [
        c
        for c in initial_result["conflicts"]
        if c.get("severity") == "HARD"
        and not c.get("resolved", False)
        and c.get("conflict_type") in ("UNCOVERED_BRAND_PROCESS", "INSUFFICIENT_STAFFING")
        and c.get("brand_id")
        and c.get("process_id")
    ]
    coverage_conflicts.sort(
        key=lambda c: (c["date"], c.get("brand_id") or "", c.get("process_id") or "")
    )

    for conf in coverage_conflicts:
        d_str = conf["date"]
        b_id = conf["brand_id"]
        p_id = conf["process_id"]

        for cand in conf.get("suggested_resolutions", []):
            cand_id = cand.get("employee_id")
            score = int(cand.get("score", 0))
            if not cand_id or score < min_score:
                continue
            if cand_id in assigned_backups_by_date[d_str]:
                continue

            entry = entry_by_emp_date.get((cand_id, d_str))
            if not entry or entry.get("status") != "WORKING":
                continue

            # Guard against triggering SHIFT_OR_OVERLOAD_CONFLICT (>3 brands on same day)
            if len(emp_primary_brands[cand_id] | {b_id}) > 3:
                continue

            entry["status"] = "BACKUP_COVERAGE"
            entry["assigned_brand_id"] = b_id
            entry["assigned_process_id"] = p_id
            entry["is_manual_override"] = True
            entry["notes"] = f"Auto-resolved backup (score {score})"
            assigned_backups_by_date[d_str].add(cand_id)
            break

    updated_roster = recalculate_coverage_and_validate(
        month_str=month_str,
        entries=working_entries,
        employees=employees,
        brands=brands,
        processes=processes,
        brand_process_rules=brand_process_rules,
        allocations=allocations,
        public_holidays=public_holidays,
        leaves_and_compoffs=leaves_and_compoffs,
        roster_status=roster_status,
        generated_at=generated_at,
    )

    coverage_after = float(updated_roster["kpis"]["coverage_percentage"])
    remaining_hard_conflicts = int(updated_roster["kpis"]["hard_conflicts_count"])
    resolved_count = max(0, hard_before - remaining_hard_conflicts)
    structural_gaps_summary = _build_structural_gaps_summary(
        updated_roster["conflicts"],
        min_score=min_score,
    )

    return {
        "resolved_count": resolved_count,
        "remaining_hard_conflicts": remaining_hard_conflicts,
        "coverage_before": coverage_before,
        "coverage_after": coverage_after,
        "structural_gaps_summary": structural_gaps_summary,
        "roster": updated_roster,
    }
