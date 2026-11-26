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
    # Strict Pareto-optimality of BALANCED between COVERAGE_FIRST and PREFERENCE_FIRST
    assert balanced["kpis"]["coverage_percentage"] > pref_first["kpis"]["coverage_percentage"]
    assert balanced["kpis"]["hard_conflicts_count"] < pref_first["kpis"]["hard_conflicts_count"]
    assert balanced["kpis"]["soft_conflicts_count"] < cov_first["kpis"]["soft_conflicts_count"]
    assert cov_first["kpis"]["coverage_percentage"] >= balanced["kpis"]["coverage_percentage"]
    assert cov_first["kpis"]["hard_conflicts_count"] <= balanced["kpis"]["hard_conflicts_count"]
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
    from routers import rosters as rosters_router

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    rosters_router._AI_EXPLAIN_CACHE.clear()

    payload = {
        "date": "2026-12-02",
        "conflict_type": "UNCOVERED_BRAND_PROCESS",
        "severity": "HARD",
        "brand_id": "BRD-02",
        "process_id": "PROC-CS",
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
    }

    resp = client.post("/api/rosters/2026-12/explain-conflict", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "Deterministic Fallback"
    assert len(body["explanation"]) > 10
    assert len(body["action_steps"]) >= 2
    assert len(rosters_router._AI_EXPLAIN_CACHE) == 1

    # Repeat call must return cached response immediately without recomputing
    def _fail_if_recomputed(_payload):
        raise AssertionError("Should have returned cached explanation")

    monkeypatch.setattr(rosters_router, "_deterministic_explain", _fail_if_recomputed)
    resp_cached = client.post("/api/rosters/2026-12/explain-conflict", json=payload)
    assert resp_cached.status_code == 200
    assert resp_cached.json() == body


def test_reset_seed_restores_lv07(client: TestClient):
    # Approve LV-07 so its state diverges from canonical sample_data.json
    approve_resp = client.post("/api/leaves/LV-07/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.json()["leave"]["status"] == "APPROVED"

    # Reset seed must restore LV-07 to PENDING with original employee/dates
    reset_resp = client.post("/api/admin/reset-seed")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == "ok"

    lv07_resp = client.get("/api/leaves/LV-07")
    assert lv07_resp.status_code == 200
    lv07 = lv07_resp.json()
    assert lv07["id"] == "LV-07"
    assert lv07["employee_id"] == "EMP-12"
    assert lv07["start_date"] == "2026-12-16"
    assert lv07["end_date"] == "2026-12-17"
    assert lv07["status"] == "PENDING"


def test_balanced_multi_resource_rotational_staggering():
    """Verify BALANCED staggers colliding ROTATIONAL peers onto lowest-demand non-peak weekdays."""
    employees = [
        {
            "id": "EMP-A",
            "name": "Alice",
            "role": "ASSOCIATE",
            "pod_id": "POD-1",
            "skills": ["PROC-CS"],
            "default_weekly_off": 6,
            "preferred_weekly_off": 6,
            "weekly_off_rule": "ROTATIONAL",
        },
        {
            "id": "EMP-B",
            "name": "Bob",
            "role": "ASSOCIATE",
            "pod_id": "POD-1",
            "skills": ["PROC-CS"],
            "default_weekly_off": 6,
            "preferred_weekly_off": 6,
            "weekly_off_rule": "ROTATIONAL",
        },
    ]
    brands = [{"id": "BRD-X", "name": "Brand X", "pod_id": "POD-1", "staffing_model": "MULTI_RESOURCE"}]
    processes = [{"id": "PROC-CS", "code": "CS", "name": "Customer Support"}]
    rules = [
        {
            "id": "BPR-X",
            "brand_id": "BRD-X",
            "process_id": "PROC-CS",
            "calendar_type": "365_DAYS",
            "min_staffing": 1,
            "day_min_staffing_overrides": {"0": 2, "5": 2},
        }
    ]
    allocations = [
        {"id": "ALC-A", "employee_id": "EMP-A", "brand_id": "BRD-X", "process_id": "PROC-CS", "allocation_type": "PRIMARY"},
        {"id": "ALC-B", "employee_id": "EMP-B", "brand_id": "BRD-X", "process_id": "PROC-CS", "allocation_type": "PRIMARY"},
    ]

    roster = generate_roster(
        month_str="2026-12",
        employees=employees,
        brands=brands,
        processes=processes,
        brand_process_rules=rules,
        allocations=allocations,
        public_holidays=[],
        leaves_and_compoffs=[],
        strategy="BALANCED",
    )

    assert roster["kpis"]["coverage_percentage"] == 100.0
    assert roster["kpis"]["hard_conflicts_count"] == 0
    assert not any(c["conflict_type"] == "LEAVE_OR_OFF_VIOLATION" for c in roster["conflicts"])


def test_auto_resolve_gaps_engine_and_endpoint(client: TestClient):
    """Feature 1: 1-click batch auto-resolver fills eligible gaps without double-booking."""
    from collections import Counter
    from engine.auto_resolver import auto_resolve_gaps

    dataset = load_sample_data()
    base = generate_roster(
        month_str="2026-12",
        employees=dataset["employees"],
        brands=dataset["brands"],
        processes=dataset["processes"],
        brand_process_rules=dataset["brand_process_rules"],
        allocations=dataset["allocations"],
        public_holidays=dataset["public_holidays"],
        leaves_and_compoffs=dataset["leaves_and_compoffs"],
    )

    engine_res = auto_resolve_gaps(
        month_str="2026-12",
        entries=base["entries"],
        employees=dataset["employees"],
        brands=dataset["brands"],
        processes=dataset["processes"],
        brand_process_rules=dataset["brand_process_rules"],
        allocations=dataset["allocations"],
        public_holidays=dataset["public_holidays"],
        leaves_and_compoffs=dataset["leaves_and_compoffs"],
        min_score=70,
    )
    assert engine_res["resolved_count"] > 0
    assert engine_res["coverage_after"] >= engine_res["coverage_before"]
    assert engine_res["remaining_hard_conflicts"] < base["kpis"]["hard_conflicts_count"]
    assert isinstance(engine_res["structural_gaps_summary"], str)
    assert len(engine_res["structural_gaps_summary"].strip()) > 0

    # Verify max 1 backup assignment per employee per date
    per_date_emp_backups = Counter(
        (e["date"], e["employee_id"])
        for e in engine_res["roster"]["entries"]
        if e["status"] == "BACKUP_COVERAGE"
    )
    assert all(cnt <= 1 for cnt in per_date_emp_backups.values())

    # 404 on missing roster
    assert client.post("/api/admin/reset-seed").status_code == 200
    missing_resp = client.post("/api/rosters/2026-11/auto-resolve")
    assert missing_resp.status_code == 404

    # Generate fresh roster and test endpoint + persistence + PUBLISHED notification
    assert client.post("/api/rosters/generate?month=2026-12").status_code == 200
    assert client.post("/api/rosters/2026-12/publish", json={"force": True, "actor_role": "OPS_MANAGER"}).status_code == 200

    api_resp = client.post("/api/rosters/2026-12/auto-resolve")
    assert api_resp.status_code == 200, api_resp.text
    body = api_resp.json()
    assert body["resolved_count"] > 0
    assert body["coverage_after"] >= body["coverage_before"]
    assert len(body["structural_gaps_summary"].strip()) > 0
    assert body["roster"]["kpis"]["coverage_percentage"] == body["coverage_after"]
    assert body["roster"]["kpis"]["hard_conflicts_count"] == body["remaining_hard_conflicts"]

    # Ensure persisted roster reflects the auto-resolved state
    fetched = client.get("/api/rosters/2026-12").json()
    assert fetched["kpis"]["coverage_percentage"] == body["coverage_after"]
    assert fetched["kpis"]["hard_conflicts_count"] == body["remaining_hard_conflicts"]

    # Ensure max 1 backup per employee per date in persisted entries
    persisted_backups = Counter(
        (e["date"], e["employee_id"])
        for e in fetched["entries"]
        if e["status"] == "BACKUP_COVERAGE"
    )
    assert all(cnt <= 1 for cnt in persisted_backups.values())

    # Ensure AUTO_RESOLVED notification was created for PUBLISHED roster
    notifs = client.get("/api/notifications?month=2026-12").json()
    assert any(n["event_type"] == "AUTO_RESOLVED" for n in notifs)


def test_bottlenecks_engine_and_endpoint(client: TestClient):
    """Feature 3: Operational bottleneck analysis identifies top pods, brands, and recommendations."""
    from engine.bottlenecks import analyze_bottlenecks

    dataset = load_sample_data()

    # Empty / soft-only conflicts edge case
    empty_res = analyze_bottlenecks(
        conflicts=[{"severity": "SOFT", "conflict_type": "PREFERENCE_VIOLATED", "brand_id": "BRD-01"}],
        employees=dataset["employees"],
        brands=dataset["brands"],
        pods=dataset["pods"],
    )
    assert empty_res["total_hard_conflicts"] == 0
    assert empty_res["top_pods"] == []
    assert empty_res["top_brands"] == []
    assert empty_res["recommendations"] == []

    # 404 when roster does not exist (reset seed first so prior test overrides do not carry over)
    assert client.post("/api/admin/reset-seed").status_code == 200
    assert client.get("/api/rosters/2026-11/bottlenecks").status_code == 404

    # Generate 2026-12 roster and check bottlenecks
    assert client.post("/api/rosters/generate?month=2026-12").status_code == 200
    resp = client.get("/api/rosters/2026-12/bottlenecks")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["total_hard_conflicts"] > 0
    assert 1 <= len(data["top_pods"]) <= 3
    assert 1 <= len(data["top_brands"]) <= 3
    assert len(data["recommendations"]) == len(data["top_pods"])

    # Verify descending order and concrete recommendation content
    pod_counts = [p["hard_conflicts_count"] for p in data["top_pods"]]
    assert pod_counts == sorted(pod_counts, reverse=True)
    brand_counts = [b["hard_conflicts_count"] for b in data["top_brands"]]
    assert brand_counts == sorted(brand_counts, reverse=True)

    top_pod = data["top_pods"][0]
    assert top_pod["pod_id"] == "POD-1"
    assert top_pod["pod_name"] in data["recommendations"][0]
    assert top_pod["pod_id"] in data["recommendations"][0]

    # After auto-resolve, persisted bottlenecks must reflect reduced hard conflicts
    ar_resp = client.post("/api/rosters/2026-12/auto-resolve")
    assert ar_resp.status_code == 200
    after_resp = client.get("/api/rosters/2026-12/bottlenecks")
    assert after_resp.status_code == 200
    after_data = after_resp.json()
    assert after_data["total_hard_conflicts"] == ar_resp.json()["remaining_hard_conflicts"]
    assert after_data["total_hard_conflicts"] < data["total_hard_conflicts"]


def test_explain_conflict_ai_provider_timeout_and_cache(client: TestClient, monkeypatch):
    """Verify timeout=8.0, AI provider caching on hit, and Deterministic Fallback on timeout."""
    import httpx
    from routers import rosters as rosters_router

    rosters_router._AI_EXPLAIN_CACHE.clear()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    call_log = []

    class _FakeSuccessResp:
        status_code = 200

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"explanation": "Cached AI insight.", "action_steps": ["Step 1", "Step 2"]}'
                        }
                    }
                ]
            }

    class _FakeClientSuccess:
        def __init__(self, timeout=None):
            call_log.append(timeout)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return _FakeSuccessResp()

    monkeypatch.setattr(rosters_router.httpx, "Client", _FakeClientSuccess)
    payload_ok = {
        "date": "2026-12-03",
        "conflict_type": "UNCOVERED_BRAND_PROCESS",
        "severity": "HARD",
        "brand_id": "BRD-17",
        "process_id": "PROC-ACC",
        "brand_name": "AuraSkin Labs",
        "process_name": "ACC",
        "message": "Gap on 2026-12-03",
        "suggested_resolutions": [],
    }
    res1 = client.post("/api/rosters/2026-12/explain-conflict", json=payload_ok)
    assert res1.status_code == 200
    assert res1.json()["provider"].startswith("OpenRouter")
    assert call_log == [8.0]

    # Repeat call hits cache with zero extra HTTP requests
    res2 = client.post("/api/rosters/2026-12/explain-conflict", json=payload_ok)
    assert res2.status_code == 200
    assert res2.json() == res1.json()
    assert call_log == [8.0]

    # Timeout across providers falls back to Deterministic Fallback
    class _FakeClientTimeout:
        def __init__(self, timeout=None):
            call_log.append(timeout)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(rosters_router.httpx, "Client", _FakeClientTimeout)
    payload_timeout = dict(payload_ok, date="2026-12-04", message="Timeout gap")
    res_timeout = client.post("/api/rosters/2026-12/explain-conflict", json=payload_timeout)
    assert res_timeout.status_code == 200
    assert res_timeout.json()["provider"] == "Deterministic Fallback"
    rosters_router._AI_EXPLAIN_CACHE.clear()


def test_auto_resolve_respects_min_score_and_existing_backups():
    """Verify auto_resolve_gaps skips candidates already on BACKUP_COVERAGE and below min_score."""
    from engine.auto_resolver import auto_resolve_gaps
    from engine.scheduler import get_month_dates

    employees = [
        {
            "id": "EMP-P",
            "name": "Primary",
            "role": "ASSOCIATE",
            "pod_id": "POD-1",
            "skills": ["PROC-CS"],
            "default_weekly_off": 6,
            "preferred_weekly_off": 6,
            "weekly_off_rule": "FIXED",
            "is_floater": False,
            "active": True,
        },
        {
            "id": "EMP-F",
            "name": "Floater",
            "role": "ASSOCIATE",
            "pod_id": "POD-1",
            "skills": ["PROC-CS"],
            "default_weekly_off": 5,
            "preferred_weekly_off": 5,
            "weekly_off_rule": "FIXED",
            "is_floater": True,
            "active": True,
        },
        {
            "id": "EMP-CROSS",
            "name": "CrossFloater",
            "role": "ASSOCIATE",
            "pod_id": "POD-2",
            "skills": ["PROC-CS"],
            "default_weekly_off": 4,
            "preferred_weekly_off": 4,
            "weekly_off_rule": "FIXED",
            "is_floater": True,
            "active": True,
        },
    ]
    brands = [{"id": "BRD-1", "name": "Brand 1", "pod_id": "POD-1", "staffing_model": "SINGLE_RESOURCE"}]
    processes = [{"id": "PROC-CS", "code": "CS", "name": "Customer Support"}]
    rules = [
        {
            "id": "BPR-1",
            "brand_id": "BRD-1",
            "process_id": "PROC-CS",
            "calendar_type": "365_DAYS",
            "min_staffing": 1,
            "day_min_staffing_overrides": {},
        }
    ]
    allocations = [
        {"id": "ALC-1", "employee_id": "EMP-P", "brand_id": "BRD-1", "process_id": "PROC-CS", "allocation_type": "PRIMARY"},
    ]

    entries = []
    for d_obj in get_month_dates("2026-12"):
        d_str = d_obj.strftime("%Y-%m-%d")
        entries.append({
            "employee_id": "EMP-P",
            "date": d_str,
            "status": "WEEKLY_OFF" if d_obj.weekday() == 6 else "WORKING",
            "assigned_brand_id": None,
            "assigned_process_id": None,
            "is_manual_override": False,
            "notes": None,
        })
        # On 2026-12-06 (Sunday), EMP-F is ALREADY assigned as BACKUP_COVERAGE elsewhere
        if d_str == "2026-12-06":
            entries.append({
                "employee_id": "EMP-F",
                "date": d_str,
                "status": "BACKUP_COVERAGE",
                "assigned_brand_id": "BRD-OTHER",
                "assigned_process_id": "PROC-CS",
                "is_manual_override": True,
                "notes": "Existing backup",
            })
        else:
            entries.append({
                "employee_id": "EMP-F",
                "date": d_str,
                "status": "WEEKLY_OFF" if d_obj.weekday() == 5 else "WORKING",
                "assigned_brand_id": None,
                "assigned_process_id": None,
                "is_manual_override": False,
                "notes": None,
            })
        entries.append({
            "employee_id": "EMP-CROSS",
            "date": d_str,
            "status": "WEEKLY_OFF" if d_obj.weekday() == 4 else "WORKING",
            "assigned_brand_id": None,
            "assigned_process_id": None,
            "is_manual_override": False,
            "notes": None,
        })

    res = auto_resolve_gaps(
        month_str="2026-12",
        entries=entries,
        employees=employees,
        brands=brands,
        processes=processes,
        brand_process_rules=rules,
        allocations=allocations,
        public_holidays=[],
        leaves_and_compoffs=[],
        min_score=70,
    )

    # 2026-12-06 must remain unresolved (EMP-F already BACKUP_COVERAGE, EMP-CROSS score 60 < 70)
    dec6_emp_f = next(e for e in res["roster"]["entries"] if e["employee_id"] == "EMP-F" and e["date"] == "2026-12-06")
    assert dec6_emp_f["assigned_brand_id"] == "BRD-OTHER"
    assert res["remaining_hard_conflicts"] == 1

    # Other Sundays (13, 20, 27) should be auto-resolved using EMP-F (score 100 >= 70)
    assert res["resolved_count"] == 3
    dec13_emp_f = next(e for e in res["roster"]["entries"] if e["employee_id"] == "EMP-F" and e["date"] == "2026-12-13")
    assert dec13_emp_f["status"] == "BACKUP_COVERAGE"
    assert dec13_emp_f["assigned_brand_id"] == "BRD-1"
    assert dec13_emp_f["is_manual_override"] is True
    assert dec13_emp_f["notes"] == "Auto-resolved backup (score 100)"


