import io
import os
import sys
import openpyxl
import pytest
from fastapi.testclient import TestClient

# Ensure backend directory is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app
from seed import load_sample_data, seed_database
from engine.scheduler import generate_roster


@pytest.fixture(scope="module")
def client():
    seed_database()
    with TestClient(app) as c:
        yield c
    # Restore clean seed state after module
    seed_database()


def test_scheduler_strategies_and_fairness():
    dataset = load_sample_data()
    cov_first = generate_roster(
        month_str="2026-12",
        employees=dataset["employees"],
        brands=dataset["brands"],
        processes=dataset["processes"],
        brand_process_rules=dataset["brand_process_rules"],
        allocations=dataset["allocations"],
        public_holidays=dataset["public_holidays"],
        leaves_and_compoffs=dataset["leaves_and_compoffs"],
        strategy="COVERAGE_FIRST",
    )
    balanced = generate_roster(
        month_str="2026-12",
        employees=dataset["employees"],
        brands=dataset["brands"],
        processes=dataset["processes"],
        brand_process_rules=dataset["brand_process_rules"],
        allocations=dataset["allocations"],
        public_holidays=dataset["public_holidays"],
        leaves_and_compoffs=dataset["leaves_and_compoffs"],
        strategy="BALANCED",
    )
    pref_first = generate_roster(
        month_str="2026-12",
        employees=dataset["employees"],
        brands=dataset["brands"],
        processes=dataset["processes"],
        brand_process_rules=dataset["brand_process_rules"],
        allocations=dataset["allocations"],
        public_holidays=dataset["public_holidays"],
        leaves_and_compoffs=dataset["leaves_and_compoffs"],
        strategy="PREFERENCE_FIRST",
    )

    assert "fairness_summary" in balanced["kpis"]
    assert len(balanced["kpis"]["fairness_summary"]["per_employee"]) == len(dataset["employees"])
    # Preference-first must not emit PREFERENCE_VIOLATED soft conflicts
    assert not any(c["conflict_type"] == "PREFERENCE_VIOLATED" for c in pref_first["conflicts"])
    # Coverage-first should have >= coverage of preference-first
    assert cov_first["kpis"]["coverage_percentage"] >= pref_first["kpis"]["coverage_percentage"]
    # Balanced Sunday rotation must not introduce 7-day stretch violations
    assert not any(
        c["conflict_type"] == "LEAVE_OR_OFF_VIOLATION" and "7-day stretch" in c["message"]
        for c in balanced["conflicts"]
    )


def test_compare_and_apply_plans(client: TestClient):
    resp = client.post("/api/rosters/2026-12/compare-plans")
    assert resp.status_code == 200
    data = resp.json()
    assert data["month"] == "2026-12"
    strategies = {p["strategy"] for p in data["plans"]}
    assert strategies == {"COVERAGE_FIRST", "BALANCED", "PREFERENCE_FIRST"}
    for plan in data["plans"]:
        assert "coverage_percentage" in plan["kpis"]
        assert "fairness_summary" in plan["kpis"]

    apply_resp = client.post("/api/rosters/2026-12/apply-plan?strategy=COVERAGE_FIRST")
    assert apply_resp.status_code == 200
    applied = apply_resp.json()
    assert applied["status"] == "DRAFT"
    assert applied["month"] == "2026-12"


def test_approval_workflow_and_publish_notifications(client: TestClient):
    # Ensure fresh roster
    gen_resp = client.post("/api/rosters/generate?month=2026-12")
    assert gen_resp.status_code == 200
    assert gen_resp.json()["status"] == "DRAFT"

    # Pod Lead approval
    pod_resp = client.post("/api/rosters/2026-12/approve-pod", json={"actor_role": "POD_LEAD"})
    assert pod_resp.status_code == 200
    assert pod_resp.json()["status"] == "POD_APPROVED"

    # Publish without force should fail with 409 because sample_data has hard conflicts (DEMO-1/DEMO-2)
    pub_fail = client.post("/api/rosters/2026-12/publish", json={"force": False, "actor_role": "OPS_MANAGER"})
    assert pub_fail.status_code == 409
    fail_body = pub_fail.json()
    assert fail_body["requires_force"] is True
    assert fail_body["hard_conflicts_count"] > 0

    # Publish with force=True succeeds
    pub_ok = client.post("/api/rosters/2026-12/publish", json={"force": True, "actor_role": "OPS_MANAGER"})
    assert pub_ok.status_code == 200
    assert pub_ok.json()["status"] == "PUBLISHED"

    # Edit entry on published roster -> triggers ENTRY_EDITED notification
    patch_resp = client.patch(
        "/api/rosters/2026-12/entry",
        json={
            "employee_id": "EMP-06",
            "date": "2026-12-02",
            "status": "WORKING",
            "notes": "Emergency coverage",
        },
    )
    assert patch_resp.status_code == 200

    # Assign backup on published roster -> triggers BACKUP_ASSIGNED notification
    bk_resp = client.post(
        "/api/rosters/2026-12/assign-backup",
        json={
            "date": "2026-12-09",
            "brand_id": "BRD-02",
            "process_id": "PROC-CS",
            "backup_employee_id": "EMP-01",
        },
    )
    assert bk_resp.status_code == 200

    # Approve leave on published roster -> triggers LEAVE_APPROVED notification
    lv_resp = client.post("/api/leaves/LV-07/approve")
    assert lv_resp.status_code == 200

    # Check notifications endpoints
    notif_resp = client.get("/api/notifications?month=2026-12")
    assert notif_resp.status_code == 200
    notifs = notif_resp.json()
    event_types = [n["event_type"] for n in notifs]
    assert "POD_APPROVED" in event_types
    assert "PUBLISHED" in event_types
    assert "ENTRY_EDITED" in event_types
    assert "BACKUP_ASSIGNED" in event_types
    assert "LEAVE_APPROVED" in event_types
    # Ordered newest first
    assert notifs[0]["id"] > notifs[-1]["id"]

    # Alias endpoint
    alias_resp = client.get("/api/rosters/notifications?month=2026-12")
    assert alias_resp.status_code == 200
    assert len(alias_resp.json()) == len(notifs)

    # Mark all read
    mark_resp = client.post("/api/notifications/mark-read")
    assert mark_resp.status_code == 200
    assert mark_resp.json()["updated"] >= 5

    after_mark = client.get("/api/notifications?month=2026-12").json()
    assert all(n["is_read"] is True for n in after_mark)


def test_export_xlsx(client: TestClient):
    resp = client.get("/api/rosters/2026-12/export.xlsx")
    assert resp.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in resp.headers["content-type"]
    assert 'filename="roster-2026-12.xlsx"' in resp.headers["content-disposition"]

    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    assert wb.sheetnames == ["Roster Matrix", "Coverage Summary", "Conflicts"]
    assert wb["Roster Matrix"].max_row > 1
    assert wb["Coverage Summary"].max_row > 1


def test_explain_conflict_deterministic_fallback(client: TestClient, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    resp = client.post(
        "/api/rosters/2026-12/explain-conflict",
        json={
            "date": "2026-12-02",
            "conflict_type": "UNCOVERED_BRAND_PROCESS",
            "severity": "HARD",
            "brand_name": "VelvetDew Skincare",
            "process_name": "CS",
            "employee_name": None,
            "message": "Brand VelvetDew Skincare requires 1 staff for CS on 2026-12-02, but 0 employees are covering (UNCOVERED).",
            "suggested_resolutions": [
                {
                    "employee_id": "EMP-05",
                    "name": "Sneha Nair",
                    "score": 85,
                    "tier": "SAME_POD_FLOATER",
                    "reason": "Same pod floater available",
                }
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "Deterministic Smart Engine"
    assert len(body["explanation"]) > 10
    assert len(body["action_steps"]) >= 2
