"""
Deterministic Operational Bottleneck Analyzer.
PURE DETERMINISTIC LOGIC - NO FASTAPI OR DATABASE CALLS.
"""
from collections import Counter, defaultdict
from typing import Any, Dict, List, Set


def analyze_bottlenecks(
    conflicts: List[Dict[str, Any]],
    employees: List[Dict[str, Any]],
    brands: List[Dict[str, Any]],
    pods: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Analyze unresolved HARD conflicts to identify top bottleneck pods and brands,
    plus concrete hiring and cross-training recommendations.
    """
    brand_dict = {b["id"]: b for b in brands}
    pod_dict = {p["id"]: p for p in pods}
    emp_dict = {e["id"]: e for e in employees}

    hard_conflicts = [
        c
        for c in conflicts
        if c.get("severity") == "HARD" and not c.get("resolved", False)
    ]
    total_hard = len(hard_conflicts)

    if total_hard == 0:
        return {
            "total_hard_conflicts": 0,
            "top_pods": [],
            "top_brands": [],
            "recommendations": [],
        }

    pod_hard_counts: Counter[str] = Counter()
    brand_hard_counts: Counter[str] = Counter()
    pod_dates: Dict[str, Set[str]] = defaultdict(set)
    pod_brands: Dict[str, Set[str]] = defaultdict(set)
    pod_processes: Dict[str, Counter[str]] = defaultdict(Counter)

    for conf in hard_conflicts:
        b_id = conf.get("brand_id")
        e_id = conf.get("employee_id")
        p_id = conf.get("process_id")
        d_str = conf.get("date")

        pod_id: str | None = None
        if b_id and b_id in brand_dict:
            brand_hard_counts[b_id] += 1
            pod_id = brand_dict[b_id].get("pod_id")
        elif e_id and e_id in emp_dict:
            pod_id = emp_dict[e_id].get("pod_id")

        if pod_id:
            pod_hard_counts[pod_id] += 1
            if d_str:
                pod_dates[pod_id].add(d_str)
            if b_id:
                pod_brands[pod_id].add(b_id)
            if p_id:
                pod_processes[pod_id][p_id] += 1

    sorted_pods = sorted(pod_hard_counts.items(), key=lambda item: (-item[1], item[0]))[:3]
    sorted_brands = sorted(brand_hard_counts.items(), key=lambda item: (-item[1], item[0]))[:3]

    top_pods: List[Dict[str, Any]] = []
    recommendations: List[str] = []

    for pod_id, count in sorted_pods:
        pod_info = pod_dict.get(pod_id, {})
        pod_name = pod_info.get("name", pod_id)
        distinct_dates = len(pod_dates[pod_id])
        top_pods.append(
            {
                "pod_id": pod_id,
                "pod_name": pod_name,
                "hard_conflicts_count": count,
                "share_percentage": round((count / total_hard) * 100, 1),
                "affected_brands_count": len(pod_brands[pod_id]),
                "distinct_gap_dates": distinct_dates,
            }
        )

        resolvable = min(count, distinct_dates) if distinct_dates > 0 else count
        top_procs = [
            proc_id
            for proc_id, _ in sorted(
                pod_processes[pod_id].items(), key=lambda item: (-item[1], item[0])
            )[:2]
        ]
        floater_count = sum(
            1
            for e in employees
            if e.get("pod_id") == pod_id and e.get("is_floater") and e.get("active", True)
        )

        detail_parts: List[str] = []
        if top_procs:
            detail_parts.append(f"prioritize cross-training on {', '.join(top_procs)}")
        if floater_count == 0:
            detail_parts.append("currently 0 dedicated floaters in pod")
        else:
            detail_parts.append(f"currently {floater_count} floater(s) in pod")
        detail_suffix = f" ({'; '.join(detail_parts)})" if detail_parts else ""

        if resolvable < count:
            recommendations.append(
                f"Adding 1 cross-trained floater to {pod_name} ({pod_id}) resolves up to "
                f"{resolvable} of {count} hard conflict(s) this month{detail_suffix}."
            )
        else:
            recommendations.append(
                f"Adding 1 cross-trained floater to {pod_name} ({pod_id}) resolves up to "
                f"{count} hard conflict(s) this month{detail_suffix}."
            )

    top_brands: List[Dict[str, Any]] = []
    for brand_id, count in sorted_brands:
        brand_info = brand_dict.get(brand_id, {})
        pod_id = brand_info.get("pod_id", "")
        pod_name = pod_dict.get(pod_id, {}).get("name", pod_id)
        top_brands.append(
            {
                "brand_id": brand_id,
                "brand_name": brand_info.get("name", brand_id),
                "pod_id": pod_id,
                "pod_name": pod_name,
                "hard_conflicts_count": count,
                "share_percentage": round((count / total_hard) * 100, 1),
            }
        )

    return {
        "total_hard_conflicts": total_hard,
        "top_pods": top_pods,
        "top_brands": top_brands,
        "recommendations": recommendations,
    }
