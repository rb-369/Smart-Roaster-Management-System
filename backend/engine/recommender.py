"""
Backup Resource Recommender Engine.
PURE DETERMINISTIC LOGIC - NO FASTAPI OR DATABASE CALLS.
"""
from typing import List, Dict, Any, Set


def recommend_backups(
    brand_id: str,
    process_id: str,
    date_str: str,
    brand_pod_id: str,
    employees: List[Dict[str, Any]],
    employee_statuses: Dict[str, str],  # emp_id -> status on date_str
    allocations: List[Dict[str, Any]],
    surplus_employee_ids: Set[str] | None = None,
) -> List[Dict[str, Any]]:
    """
    Rank top backup candidates for an uncovered or understaffed (brand, process, date).
    
    Ranking:
    1. Same-pod floaters (is_floater=True) WORKING on date with process_id in skills (Score: 100)
    2. Same-pod associates WORKING on date with process_id in skills from surplus multi-resource brand (Score: 80)
    3. Cross-pod floaters WORKING on date with process_id in skills (Score: 60)
    4. Pod Lead of the brand's pod as escalation fallback (Score: 40)
    """
    surplus_ids = surplus_employee_ids or set()
    recommendations: List[Dict[str, Any]] = []

    # Map allocations to find primary employees for this brand/process to avoid recommending someone already primary
    primary_for_this = {
        a["employee_id"] for a in allocations
        if a.get("brand_id") == brand_id and a.get("process_id") == process_id and a.get("allocation_type") == "PRIMARY"
    }

    pod_lead_candidate = None

    for emp in employees:
        emp_id = emp["id"]
        # Skip if already primary for this exact brand and process
        if emp_id in primary_for_this:
            continue
        
        status = employee_statuses.get(emp_id, "WORKING")
        is_active = emp.get("active", True)
        if not is_active:
            continue

        emp_role = emp.get("role", "ASSOCIATE")
        emp_pod_id = emp.get("pod_id")
        emp_skills = emp.get("skills", [])
        is_floater = emp.get("is_floater", False)
        has_skill = process_id in emp_skills

        # Handle Pod Lead escalation
        if emp_role == "POD_LEAD" and emp_pod_id == brand_pod_id:
            pod_lead_candidate = {
                "employee_id": emp_id,
                "name": emp.get("name", emp_id),
                "score": 40,
                "tier": "POD_LEAD_ESCALATION",
                "reason": f"Pod Lead of {brand_pod_id} (last-resort supervisory escalation)",
            }
            continue

        # For associate recommendations, they MUST be WORKING on this date
        if status not in ("WORKING", "BACKUP_COVERAGE"):
            continue

        # Must have the necessary skill
        if not has_skill:
            continue

        # 1. Same-pod floater
        if emp_pod_id == brand_pod_id and is_floater:
            recommendations.append({
                "employee_id": emp_id,
                "name": emp.get("name", emp_id),
                "score": 100,
                "tier": "SAME_POD_FLOATER",
                "reason": f"Same-pod dedicated floater with {process_id} skill and working on {date_str}",
            })
        # 2. Same-pod surplus associate
        elif emp_pod_id == brand_pod_id and emp_id in surplus_ids:
            recommendations.append({
                "employee_id": emp_id,
                "name": emp.get("name", emp_id),
                "score": 80,
                "tier": "SAME_POD_SURPLUS",
                "reason": f"Same-pod associate with {process_id} skill from surplus brand queue",
            })
        # 3. Cross-pod floater
        elif emp_pod_id != brand_pod_id and is_floater:
            recommendations.append({
                "employee_id": emp_id,
                "name": emp.get("name", emp_id),
                "score": 60,
                "tier": "CROSS_POD_FLOATER",
                "reason": f"Cross-pod floater ({emp_pod_id}) with {process_id} skill and working on {date_str}",
            })
        # General same-pod associate with skill (fallback score 70 if not explicitly flagged surplus)
        elif emp_pod_id == brand_pod_id:
            recommendations.append({
                "employee_id": emp_id,
                "name": emp.get("name", emp_id),
                "score": 70,
                "tier": "SAME_POD_ASSOCIATE",
                "reason": f"Same-pod associate with {process_id} skill available on {date_str}",
            })

    # Sort associate recommendations descending by score
    recommendations.sort(key=lambda x: x["score"], reverse=True)

    # Keep top 3 associate recommendations
    final_recs = recommendations[:3]

    # Always include Pod Lead escalation at the end as explicit fallback
    if pod_lead_candidate and pod_lead_candidate["employee_id"] not in [r["employee_id"] for r in final_recs]:
        final_recs.append(pod_lead_candidate)

    return final_recs
"""
Backup Resource Recommender Engine.
PURE DETERMINISTIC LOGIC - NO FASTAPI OR DATABASE CALLS.
"""
from typing import List, Dict, Any, Set


def recommend_backups(
    brand_id: str,
    process_id: str,
    date_str: str,
    brand_pod_id: str,
    employees: List[Dict[str, Any]],
    employee_statuses: Dict[str, str],  # emp_id -> status on date_str
    allocations: List[Dict[str, Any]],
    surplus_employee_ids: Set[str] | None = None,
) -> List[Dict[str, Any]]:
    """
    Rank top backup candidates for an uncovered or understaffed (brand, process, date).
    
    Ranking:
    1. Same-pod floaters (is_floater=True) WORKING on date with process_id in skills (Score: 100)
    2. Same-pod associates WORKING on date with process_id in skills from surplus multi-resource brand (Score: 80)
    3. Cross-pod floaters WORKING on date with process_id in skills (Score: 60)
    4. Pod Lead of the brand's pod as escalation fallback (Score: 40)
    """
    surplus_ids = surplus_employee_ids or set()
    recommendations: List[Dict[str, Any]] = []

    # Map allocations to find primary employees for this brand/process to avoid recommending someone already primary
    primary_for_this = {
        a["employee_id"] for a in allocations
        if a.get("brand_id") == brand_id and a.get("process_id") == process_id and a.get("allocation_type") == "PRIMARY"
    }

    pod_lead_candidate = None

    for emp in employees:
        emp_id = emp["id"]
        # Skip if already primary for this exact brand and process
        if emp_id in primary_for_this:
            continue
        
        status = employee_statuses.get(emp_id, "WORKING")
        is_active = emp.get("active", True)
        if not is_active:
            continue

        emp_role = emp.get("role", "ASSOCIATE")
        emp_pod_id = emp.get("pod_id")
        emp_skills = emp.get("skills", [])
        is_floater = emp.get("is_floater", False)
        has_skill = process_id in emp_skills

        # Handle Pod Lead escalation
        if emp_role == "POD_LEAD" and emp_pod_id == brand_pod_id:
            pod_lead_candidate = {
                "employee_id": emp_id,
                "name": emp.get("name", emp_id),
                "score": 40,
                "tier": "POD_LEAD_ESCALATION",
                "reason": f"Pod Lead of {brand_pod_id} (last-resort supervisory escalation)",
            }
            continue

        # For associate recommendations, they MUST be WORKING on this date
        if status not in ("WORKING", "BACKUP_COVERAGE"):
            continue

        # Must have the necessary skill
        if not has_skill:
            continue

        # 1. Same-pod floater
        if emp_pod_id == brand_pod_id and is_floater:
            recommendations.append({
                "employee_id": emp_id,
                "name": emp.get("name", emp_id),
                "score": 100,
                "tier": "SAME_POD_FLOATER",
                "reason": f"Same-pod dedicated floater with {process_id} skill and working on {date_str}",
            })
        # 2. Same-pod surplus associate
        elif emp_pod_id == brand_pod_id and emp_id in surplus_ids:
            recommendations.append({
                "employee_id": emp_id,
                "name": emp.get("name", emp_id),
                "score": 80,
                "tier": "SAME_POD_SURPLUS",
                "reason": f"Same-pod associate with {process_id} skill from surplus brand queue",
            })
        # 3. Cross-pod floater
        elif emp_pod_id != brand_pod_id and is_floater:
            recommendations.append({
                "employee_id": emp_id,
                "name": emp.get("name", emp_id),
                "score": 60,
                "tier": "CROSS_POD_FLOATER",
                "reason": f"Cross-pod floater ({emp_pod_id}) with {process_id} skill and working on {date_str}",
            })
        # General same-pod associate with skill (fallback score 70 if not explicitly flagged surplus)
        elif emp_pod_id == brand_pod_id:
            recommendations.append({
                "employee_id": emp_id,
                "name": emp.get("name", emp_id),
                "score": 70,
                "tier": "SAME_POD_ASSOCIATE",
                "reason": f"Same-pod associate with {process_id} skill available on {date_str}",
            })

    # Sort descending by score
    recommendations.sort(key=lambda x: x["score"], reverse=True)

    # Add Pod Lead escalation at the end if available
    if pod_lead_candidate and pod_lead_candidate["employee_id"] not in [r["employee_id"] for r in recommendations]:
        recommendations.append(pod_lead_candidate)

    # Return top 3-4 recommendations
    return recommendations[:4]

