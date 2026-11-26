import copy
import os
import sys
import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import get_session
from main import app
from models import (
    Allocation,
    Brand,
    BrandProcessRule,
    Employee,
    LeaveAndCompOff,
    Pod,
    Process,
    PublicHoliday,
)
from seed import load_sample_data
from engine.scheduler import generate_roster, preview_leave_impact


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Run each test against an isolated temporary SQLite DB to avoid cross-process contention."""
    db_file = tmp_path / "leave_preview_test.db"
    test_engine = create_engine(
        f"sqlite:///{db_file}",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(test_engine)

    data = load_sample_data()
    with Session(test_engine) as session:
        for proc in data.get("processes", []):
            session.add(Process(**proc))
        for pod in data.get("pods", []):
            session.add(Pod(**pod))
        for emp in data.get("employees", []):
            session.add(Employee(**emp))
        for brd in data.get("brands", []):
            session.add(Brand(**brd))
        for bpr in data.get("brand_process_rules", []):
            session.add(BrandProcessRule(**bpr))
        for alc in data.get("allocations", []):
            session.add(Allocation(**alc))
        for ph in data.get("public_holidays", []):
            session.add(PublicHoliday(**ph))
        for lvc in data.get("leaves_and_compoffs", []):
            session.add(LeaveAndCompOff(**lvc))
        session.commit()

    def override_get_session():
        with Session(test_engine) as session:
            yield session

    previous_override = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = override_get_session
    try:
        yield
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_session, None)
        else:
            app.dependency_overrides[get_session] = previous_override
        test_engine.dispose()


def test_preview_leave_impact_pure_engine_non_mutating():
    """Pure engine preview_leave_impact computes before/after diff without mutating inputs."""
    dataset = load_sample_data()
    roster = generate_roster(
        month_str="2026-12",
        employees=dataset["employees"],
        brands=dataset["brands"],
        processes=dataset["processes"],
        brand_process_rules=dataset["brand_process_rules"],
        allocations=dataset["allocations"],
        public_holidays=dataset["public_holidays"],
        leaves_and_compoffs=dataset["leaves_and_compoffs"],
    )

    entries_snapshot = copy.deepcopy(roster["entries"])
    leaves_snapshot = copy.deepcopy(dataset["leaves_and_compoffs"])

    impact = preview_leave_impact(
        month_str="2026-12",
        entries=roster["entries"],
        employee_id="EMP-12",
        start_date="2026-12-16",
        end_date="2026-12-17",
        leave_type="PLANNED_LEAVE",
        employees=dataset["employees"],
        brands=dataset["brands"],
        processes=dataset["processes"],
        brand_process_rules=dataset["brand_process_rules"],
        allocations=dataset["allocations"],
        public_holidays=dataset["public_holidays"],
        leaves_and_compoffs=dataset["leaves_and_compoffs"],
    )

    # Inputs must not be mutated
    assert roster["entries"] == entries_snapshot
    assert dataset["leaves_and_compoffs"] == leaves_snapshot

    assert impact["new_hard_conflicts_count"] >= 2
    assert impact["hard_conflicts_after"] == (
        impact["hard_conflicts_before"] + impact["new_hard_conflicts_count"]
    )
    assert impact["coverage_after"] < impact["coverage_before"]
    assert impact["affected_dates"] == ["2026-12-16", "2026-12-17"]
    assert {"brand_id": "BRD-06", "brand_name": "LoomVerse Apparel"} in impact["affected_brands"]
    assert "CS" in impact["affected_processes"]
    assert "NDR" in impact["affected_processes"]
    assert impact["affected_processes"] == sorted(impact["affected_processes"])
    assert len(impact["new_conflicts"]) == impact["new_hard_conflicts_count"]
    for conflict in impact["new_conflicts"]:
        assert conflict["severity"] == "HARD"
        assert "suggested_resolutions" in conflict
        assert len(conflict["suggested_resolutions"]) > 0


def test_preview_leave_impact_pure_engine_zero_new_conflicts():
    """When another primary maintains min_staffing, leave preview reports zero new hard conflicts."""
    employees = [
        {
            "id": "EMP-1",
            "name": "Alice",
            "role": "ASSOCIATE",
            "pod_id": "POD-1",
            "skills": ["CS"],
            "default_weekly_off": 6,
            "preferred_weekly_off": 6,
            "weekly_off_rule": "FIXED",
            "shift": "DAY_9_18",
            "is_floater": False,
            "active": True,
        },
        {
            "id": "EMP-2",
            "name": "Bob",
            "role": "ASSOCIATE",
            "pod_id": "POD-1",
            "skills": ["CS"],
            "default_weekly_off": 5,
            "preferred_weekly_off": 5,
            "weekly_off_rule": "FIXED",
            "shift": "DAY_9_18",
            "is_floater": False,
            "active": True,
        },
    ]
    brands = [
        {"id": "BRD-1", "name": "Brand One", "pod_id": "POD-1", "tier": "STANDARD", "staffing_model": "MULTI_RESOURCE"}
    ]
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
        {"id": "ALC-1", "employee_id": "EMP-1", "brand_id": "BRD-1", "process_id": "PROC-CS", "allocation_type": "PRIMARY"},
        {"id": "ALC-2", "employee_id": "EMP-2", "brand_id": "BRD-1", "process_id": "PROC-CS", "allocation_type": "PRIMARY"},
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
    )

    impact = preview_leave_impact(
        month_str="2026-12",
        entries=roster["entries"],
        employee_id="EMP-1",
        start_date="2026-12-15",
        end_date="2026-12-16",
        leave_type="PLANNED_LEAVE",
        employees=employees,
        brands=brands,
        processes=processes,
        brand_process_rules=rules,
        allocations=allocations,
        public_holidays=[],
        leaves_and_compoffs=[],
    )

    assert impact["new_hard_conflicts_count"] == 0
    assert impact["hard_conflicts_before"] == 0
    assert impact["hard_conflicts_after"] == 0
    assert impact["coverage_before"] == 100.0
    assert impact["coverage_after"] == 100.0
    assert impact["affected_dates"] == []
    assert impact["affected_brands"] == []
    assert impact["affected_processes"] == []
    assert impact["new_conflicts"] == []


def test_preview_endpoints_return_404_when_roster_missing():
    """Both preview endpoints must return 404 when no roster has been generated for the month."""
    res_existing = client.post("/api/leaves/LV-07/preview-impact?month=2026-12")
    assert res_existing.status_code == 404
    assert "Roster for '2026-12' not found. Generate the roster first." in res_existing.json()["detail"]

    res_adhoc = client.post(
        "/api/leaves/preview-impact?month=2026-12",
        json={
            "employee_id": "EMP-12",
            "start_date": "2026-12-16",
            "end_date": "2026-12-17",
            "type": "PLANNED_LEAVE",
        },
    )
    assert res_adhoc.status_code == 404
    assert "Roster for '2026-12' not found. Generate the roster first." in res_adhoc.json()["detail"]


def test_preview_existing_leave_lv07_no_db_mutation():
    """POST /api/leaves/LV-07/preview-impact?month=2026-12 previews BRD-06 gaps without mutating DB."""
    gen = client.post("/api/rosters/generate?month=2026-12")
    assert gen.status_code == 200
    before_roster = client.get("/api/rosters/2026-12").json()
    before_notifs = client.get("/api/notifications?month=2026-12").json()

    res = client.post("/api/leaves/LV-07/preview-impact?month=2026-12")
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["new_hard_conflicts_count"] >= 2
    assert data["hard_conflicts_after"] > data["hard_conflicts_before"]
    assert data["coverage_after"] < data["coverage_before"]
    assert "2026-12-16" in data["affected_dates"]
    assert "2026-12-17" in data["affected_dates"]
    assert any(b["brand_id"] == "BRD-06" and b["brand_name"] == "LoomVerse Apparel" for b in data["affected_brands"])
    assert "CS" in data["affected_processes"]
    assert "NDR" in data["affected_processes"]

    assert len(data["new_conflicts"]) == data["new_hard_conflicts_count"]
    for conf in data["new_conflicts"]:
        assert conf["severity"] == "HARD"
        assert "suggested_resolutions" in conf
        assert len(conf["suggested_resolutions"]) > 0

    # Zero DB mutation checks
    lv07 = client.get("/api/leaves/LV-07").json()
    assert lv07["status"] == "PENDING"

    after_roster = client.get("/api/rosters/2026-12").json()
    assert after_roster["kpis"]["hard_conflicts_count"] == before_roster["kpis"]["hard_conflicts_count"]
    emp12_dec16 = next(
        e for e in after_roster["entries"]
        if e["employee_id"] == "EMP-12" and e["date"] == "2026-12-16"
    )
    assert emp12_dec16["status"] == "WORKING"

    brd6_dec16 = next(
        c for c in after_roster["coverage_matrix"]
        if c["brand_id"] == "BRD-06" and c["process_id"] == "PROC-CS" and c["date"] == "2026-12-16"
    )
    assert brd6_dec16["status"] == "COVERED"

    after_notifs = client.get("/api/notifications?month=2026-12").json()
    assert after_notifs == before_notifs


def test_preview_adhoc_leave_payload_no_db_rows_added():
    """POST /api/leaves/preview-impact?month=2026-12 previews a brand-new leave with zero DB rows added."""
    gen = client.post("/api/rosters/generate?month=2026-12")
    assert gen.status_code == 200

    leaves_before = client.get("/api/leaves").json()
    roster_before = client.get("/api/rosters/2026-12").json()

    res = client.post(
        "/api/leaves/preview-impact?month=2026-12",
        json={
            "employee_id": "EMP-12",
            "start_date": "2026-12-16",
            "end_date": "2026-12-17",
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["new_hard_conflicts_count"] >= 2
    assert data["hard_conflicts_after"] > data["hard_conflicts_before"]
    assert data["coverage_after"] < data["coverage_before"]
    assert "2026-12-16" in data["affected_dates"]
    assert "2026-12-17" in data["affected_dates"]
    assert any(b["brand_id"] == "BRD-06" for b in data["affected_brands"])
    for conf in data["new_conflicts"]:
        assert "suggested_resolutions" in conf
        assert len(conf["suggested_resolutions"]) > 0

    # Zero DB rows added & roster unchanged
    leaves_after = client.get("/api/leaves").json()
    assert leaves_after == leaves_before

    roster_after = client.get("/api/rosters/2026-12").json()
    assert roster_after["kpis"] == roster_before["kpis"]


def test_preview_missing_leave_and_invalid_dates():
    """Missing leave_id returns 404; invalid date range returns 400/422."""
    assert client.post("/api/rosters/generate?month=2026-12").status_code == 200

    res_missing = client.post("/api/leaves/LV-999/preview-impact?month=2026-12")
    assert res_missing.status_code == 404

    res_bad_range = client.post(
        "/api/leaves/preview-impact?month=2026-12",
        json={
            "employee_id": "EMP-12",
            "start_date": "2026-12-18",
            "end_date": "2026-12-16",
            "type": "PLANNED_LEAVE",
        },
    )
    assert res_bad_range.status_code in (400, 422)
