import csv
import io
import pytest
from fastapi.testclient import TestClient

from main import app
from seed import seed_database

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_db_before_test():
    seed_database()
    yield


def test_crud_all_entities_and_leaves():
    # 1. Pods CRUD
    res = client.get("/api/pods")
    assert res.status_code == 200
    assert len(res.json()) == 4

    res = client.post("/api/pods", json={"name": "Pod Test", "lead_employee_id": "EMP-01"})
    assert res.status_code == 200, res.text
    pod = res.json()
    assert pod["id"].startswith("POD-")
    pod_id = pod["id"]

    res = client.put(f"/api/pods/{pod_id}", json={"name": "Pod Updated"})
    assert res.status_code == 200
    assert res.json()["name"] == "Pod Updated"

    res = client.delete(f"/api/pods/{pod_id}")
    assert res.status_code == 200
    assert client.get(f"/api/pods/{pod_id}").status_code == 404

    # 2. Processes CRUD
    res = client.get("/api/processes")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    res = client.post(
        "/api/processes",
        json={"code": "QA", "name": "Quality Assurance", "description": "QA checks"},
    )
    assert res.status_code == 200, res.text
    proc_id = res.json()["id"]
    assert proc_id.startswith("PROC-")

    res = client.put(f"/api/processes/{proc_id}", json={"name": "QA Updated"})
    assert res.status_code == 200
    assert res.json()["name"] == "QA Updated"

    assert client.delete(f"/api/processes/{proc_id}").status_code == 200

    # 3. Employees CRUD
    res = client.get("/api/employees")
    assert res.status_code == 200
    assert len(res.json()) == 32

    res = client.post(
        "/api/employees",
        json={
            "name": "Test Associate",
            "email": "test.assoc@example.com",
            "role": "ASSOCIATE",
            "pod_id": "POD-1",
            "skills": ["CS"],
        },
    )
    assert res.status_code == 200, res.text
    emp_id = res.json()["id"]
    assert emp_id.startswith("EMP-")

    res = client.put(f"/api/employees/{emp_id}", json={"is_floater": True})
    assert res.status_code == 200
    assert res.json()["is_floater"] is True

    assert client.delete(f"/api/employees/{emp_id}").status_code == 200

    # 4. Brands CRUD
    res = client.get("/api/brands")
    assert res.status_code == 200
    assert len(res.json()) == 20

    res = client.post(
        "/api/brands",
        json={"name": "Test Brand", "pod_id": "POD-1", "tier": "STANDARD"},
    )
    assert res.status_code == 200, res.text
    brd_id = res.json()["id"]
    assert brd_id.startswith("BRD-")

    res = client.put(f"/api/brands/{brd_id}", json={"tier": "ENTERPRISE"})
    assert res.status_code == 200
    assert res.json()["tier"] == "ENTERPRISE"

    # 5. Rules CRUD
    res = client.get("/api/rules")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    res = client.post(
        "/api/rules",
        json={
            "brand_id": brd_id,
            "process_id": "PROC-CS",
            "calendar_type": "365_DAYS",
            "min_staffing": 1,
        },
    )
    assert res.status_code == 200, res.text
    rule_id = res.json()["id"]
    assert rule_id.startswith("BPR-")

    res = client.put(f"/api/rules/{rule_id}", json={"min_staffing": 2})
    assert res.status_code == 200
    assert res.json()["min_staffing"] == 2

    # 6. Allocations CRUD
    res = client.get("/api/allocations")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    res = client.post(
        "/api/allocations",
        json={
            "employee_id": "EMP-02",
            "brand_id": brd_id,
            "process_id": "PROC-CS",
            "allocation_type": "BACKUP",
        },
    )
    assert res.status_code == 200, res.text
    alc_id = res.json()["id"]
    assert alc_id.startswith("ALC-")

    res = client.put(f"/api/allocations/{alc_id}", json={"allocation_type": "PRIMARY"})
    assert res.status_code == 200
    assert res.json()["allocation_type"] == "PRIMARY"

    assert client.delete(f"/api/allocations/{alc_id}").status_code == 200
    assert client.delete(f"/api/rules/{rule_id}").status_code == 200
    assert client.delete(f"/api/brands/{brd_id}").status_code == 200

    # 7. Public Holidays CRUD
    res = client.get("/api/holidays")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    res = client.post(
        "/api/holidays",
        json={"date": "2026-12-31", "name": "New Year Eve", "is_national": True},
    )
    assert res.status_code == 200, res.text
    ph_id = res.json()["id"]
    assert ph_id.startswith("PH-")

    res = client.put(f"/api/holidays/{ph_id}", json={"name": "NYE Updated"})
    assert res.status_code == 200
    assert res.json()["name"] == "NYE Updated"

    assert client.delete(f"/api/holidays/{ph_id}").status_code == 200

    # 8. Leaves CRUD + Reject
    res = client.get("/api/leaves")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    res = client.post(
        "/api/leaves",
        json={
            "employee_id": "EMP-02",
            "start_date": "2026-12-28",
            "end_date": "2026-12-29",
            "type": "PLANNED_LEAVE",
            "reason": "Personal",
        },
    )
    assert res.status_code == 200, res.text
    lv_id = res.json()["id"]
    assert lv_id.startswith("LV-")

    res = client.put(f"/api/leaves/{lv_id}", json={"reason": "Family event"})
    assert res.status_code == 200
    assert res.json()["reason"] == "Family event"

    res = client.post(f"/api/leaves/{lv_id}/reject")
    assert res.status_code == 200
    assert res.json()["status"] == "REJECTED"

    assert client.delete(f"/api/leaves/{lv_id}").status_code == 200


def test_roster_five_views():
    gen = client.post("/api/rosters/generate?month=2026-12")
    assert gen.status_code == 200

    # Company view
    res_co = client.get("/api/rosters/2026-12?view=company")
    assert res_co.status_code == 200
    co_data = res_co.json()
    assert len(co_data["entries"]) == 32 * 31

    # Pod view
    res_pod = client.get("/api/rosters/2026-12?view=pod&filter_id=POD-1")
    assert res_pod.status_code == 200
    pod_data = res_pod.json()
    assert 0 < len(pod_data["entries"]) < len(co_data["entries"])
    assert 0 < len(pod_data["coverage_matrix"]) < len(co_data["coverage_matrix"])

    # Brand view
    res_brd = client.get("/api/rosters/2026-12?view=brand&filter_id=BRD-06")
    assert res_brd.status_code == 200
    brd_data = res_brd.json()
    assert len(brd_data["coverage_matrix"]) > 0
    assert all(c["brand_id"] == "BRD-06" for c in brd_data["coverage_matrix"])

    # Process view
    res_proc = client.get("/api/rosters/2026-12?view=process&filter_id=PROC-CS")
    assert res_proc.status_code == 200
    proc_data = res_proc.json()
    assert len(proc_data["coverage_matrix"]) > 0
    assert all(c["process_id"] == "PROC-CS" for c in proc_data["coverage_matrix"])

    # Employee view
    res_emp = client.get("/api/rosters/2026-12?view=employee&filter_id=EMP-12")
    assert res_emp.status_code == 200
    emp_data = res_emp.json()
    assert len(emp_data["entries"]) == 31
    assert all(e["employee_id"] == "EMP-12" for e in emp_data["entries"])


def test_patch_entry_live_revalidation():
    assert client.post("/api/rosters/generate?month=2026-12").status_code == 200

    # EMP-12 is primary on BRD-06 PROC-CS and normally WORKING on 2026-12-16
    res = client.patch(
        "/api/rosters/2026-12/entry",
        json={
            "employee_id": "EMP-12",
            "date": "2026-12-16",
            "status": "WEEKLY_OFF",
            "notes": "Manual swap",
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    cov_16 = next(
        c for c in data["coverage_matrix"]
        if c["brand_id"] == "BRD-06" and c["process_id"] == "PROC-CS" and c["date"] == "2026-12-16"
    )
    assert cov_16["status"] == "UNCOVERED"
    assert any(
        c["brand_id"] == "BRD-06" and c["date"] == "2026-12-16" and c["severity"] == "HARD"
        for c in data["conflicts"]
    )

    # Revert back to WORKING -> conflict disappears
    res2 = client.patch(
        "/api/rosters/2026-12/entry",
        json={
            "employee_id": "EMP-12",
            "date": "2026-12-16",
            "status": "WORKING",
            "notes": "Reverted",
        },
    )
    assert res2.status_code == 200, res2.text
    data2 = res2.json()
    cov_16_after = next(
        c for c in data2["coverage_matrix"]
        if c["brand_id"] == "BRD-06" and c["process_id"] == "PROC-CS" and c["date"] == "2026-12-16"
    )
    assert cov_16_after["status"] == "COVERED"
    assert not any(
        c["brand_id"] == "BRD-06" and c["date"] == "2026-12-16" and c["severity"] == "HARD"
        for c in data2["conflicts"]
    )


def test_demo_4_end_to_end_leave_approve_and_assign_backup():
    # 1. Generate December 2026 roster
    gen = client.post("/api/rosters/generate?month=2026-12")
    assert gen.status_code == 200

    # 2. Approve LV-07 (EMP-12 on Dec 16-17)
    app_res = client.post("/api/leaves/LV-07/approve")
    assert app_res.status_code == 200, app_res.text
    app_data = app_res.json()

    assert app_data["leave"]["status"] == "APPROVED"
    impact = app_data["impact"]
    assert impact["hard_conflicts_after"] > impact["hard_conflicts_before"]
    assert "BRD-06" in impact["affected_brands"]

    brd6_conflicts = [
        c for c in app_data["roster"]["conflicts"]
        if c.get("brand_id") == "BRD-06"
        and c.get("process_id") == "PROC-CS"
        and c.get("date") == "2026-12-16"
        and c.get("severity") == "HARD"
    ]
    assert len(brd6_conflicts) == 1
    suggestions = brd6_conflicts[0]["suggested_resolutions"]
    assert len(suggestions) > 0
    top_backup_emp_id = suggestions[0]["employee_id"]

    # 3. Assign top recommended backup on 2026-12-16
    bk_res = client.post(
        "/api/rosters/2026-12/assign-backup",
        json={
            "date": "2026-12-16",
            "brand_id": "BRD-06",
            "process_id": "PROC-CS",
            "backup_employee_id": top_backup_emp_id,
        },
    )
    assert bk_res.status_code == 200, bk_res.text
    bk_data = bk_res.json()

    cov_16 = next(
        c for c in bk_data["coverage_matrix"]
        if c["brand_id"] == "BRD-06" and c["process_id"] == "PROC-CS" and c["date"] == "2026-12-16"
    )
    assert cov_16["status"] == "BACKUP_COVERED"
    assert top_backup_emp_id in cov_16["backup_employee_ids"]
    assert cov_16["working_count"] >= 1

    # Conflict for BRD-06 PROC-CS on 2026-12-16 is resolved
    assert not any(
        c.get("brand_id") == "BRD-06"
        and c.get("process_id") == "PROC-CS"
        and c.get("date") == "2026-12-16"
        and c.get("severity") == "HARD"
        for c in bk_data["conflicts"]
    )


def test_export_csv_and_reset_seed():
    assert client.post("/api/rosters/generate?month=2026-12").status_code == 200

    csv_res = client.get("/api/rosters/2026-12/export.csv")
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert 'filename="roster-2026-12.csv"' in csv_res.headers["content-disposition"]

    rows = list(csv.reader(io.StringIO(csv_res.text)))
    assert rows[0] == [
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
    ]
    assert len(rows) == 1 + (32 * 31)

    reset_res = client.post("/api/admin/reset-seed")
    assert reset_res.status_code == 200
    assert reset_res.json()["status"] == "ok"
    assert client.get("/api/rosters/2026-12").status_code == 404
