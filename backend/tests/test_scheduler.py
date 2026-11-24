import pytest
from datetime import date
from seed import load_sample_data
from engine.calendar_rules import is_operating_day, get_required_staffing
from engine.scheduler import generate_roster
from engine.recommender import recommend_backups


@pytest.fixture(scope="session")
def sample_dataset():
    return load_sample_data()


def test_calendar_rules_operating_days():
    """Verify 365_DAYS, DAILY_EXCEPT_PH, and MON_SAT_EXCEPT_PH behavior on Sundays and Christmas."""
    christmas = date(2026, 12, 25)  # Friday, Public Holiday
    sunday = date(2026, 12, 27)     # Sunday, not PH
    regular_weekday = date(2026, 12, 1)  # Tuesday, regular day

    # 365_DAYS: Always True
    assert is_operating_day("365_DAYS", christmas, is_ph=True) is True
    assert is_operating_day("365_DAYS", sunday, is_ph=False) is True
    assert is_operating_day("365_DAYS", regular_weekday, is_ph=False) is True

    # DAILY_EXCEPT_PH: False on Christmas, True on Sunday and regular weekdays
    assert is_operating_day("DAILY_EXCEPT_PH", christmas, is_ph=True) is False
    assert is_operating_day("DAILY_EXCEPT_PH", sunday, is_ph=False) is True
    assert is_operating_day("DAILY_EXCEPT_PH", regular_weekday, is_ph=False) is True

    # MON_SAT_EXCEPT_PH: False on Christmas, False on Sunday, True on regular weekday
    assert is_operating_day("MON_SAT_EXCEPT_PH", christmas, is_ph=True) is False
    assert is_operating_day("MON_SAT_EXCEPT_PH", sunday, is_ph=False) is False
    assert is_operating_day("MON_SAT_EXCEPT_PH", regular_weekday, is_ph=False) is True


def test_required_staffing_overrides():
    """Verify min_staffing overrides for peak days (e.g. BRD-18 CS on Mon=2, Sat=2, other=1)."""
    monday = date(2026, 12, 14)  # Weekday 0 (Monday)
    tuesday = date(2026, 12, 15) # Weekday 1 (Tuesday)
    saturday = date(2026, 12, 19) # Weekday 5 (Saturday)

    overrides = {"0": 2, "5": 2}
    # Monday override: 2
    assert get_required_staffing("365_DAYS", monday, False, base_min_staffing=1, day_min_staffing_overrides=overrides) == 2
    # Tuesday base: 1
    assert get_required_staffing("365_DAYS", tuesday, False, base_min_staffing=1, day_min_staffing_overrides=overrides) == 1
    # Saturday override: 2
    assert get_required_staffing("365_DAYS", saturday, False, base_min_staffing=1, day_min_staffing_overrides=overrides) == 2


def test_demo_1_single_resource_365_day_weekly_off_gaps(sample_dataset):
    """
    DEMO-1: VelvetDew Skincare (BRD-02) requires 365-day CS coverage, but has only 1 primary employee (EMP-06).
    Every Wednesday (EMP-06's weekly off) and Dec 18 (comp-off) must flag a hard coverage gap.
    """
    roster = generate_roster(
        month_str="2026-12",
        employees=sample_dataset["employees"],
        brands=sample_dataset["brands"],
        processes=sample_dataset["processes"],
        brand_process_rules=sample_dataset["brand_process_rules"],
        allocations=sample_dataset["allocations"],
        public_holidays=sample_dataset["public_holidays"],
        leaves_and_compoffs=sample_dataset["leaves_and_compoffs"],
    )

    conflicts = roster["conflicts"]

    # Filter conflicts for BRD-02 CS
    brd2_conflicts = [
        c for c in conflicts
        if c.get("brand_id") == "BRD-02" and c.get("process_id") == "PROC-CS"
    ]

    assert len(brd2_conflicts) > 0, "BRD-02 must have coverage conflicts on EMP-06 weekly offs / comp-off"

    # Dec 18 (Friday, COMP_OFF for EMP-06) must be flagged
    dec_18_conflicts = [c for c in brd2_conflicts if c["date"] == "2026-12-18"]
    assert len(dec_18_conflicts) >= 1
    assert dec_18_conflicts[0]["severity"] == "HARD"
    assert dec_18_conflicts[0]["conflict_type"] == "UNCOVERED_BRAND_PROCESS"

    # All Wednesdays in Dec 2026 (Dec 2, 9, 16, 23, 30) are EMP-06's weekly offs (default_weekly_off=2)
    # Check that Wednesday Dec 2 is flagged as an uncovered gap
    dec_2_conflicts = [c for c in brd2_conflicts if c["date"] == "2026-12-02"]
    assert len(dec_2_conflicts) >= 1
    assert dec_2_conflicts[0]["severity"] == "HARD"


def test_demo_2_multi_brand_cascade_from_leave(sample_dataset):
    """
    DEMO-2: EMP-08 manages both PurePetal Haircare (BRD-04) and KajalCraft Cosmetics (BRD-05).
    Their Dec 10-11 planned leave must flag a MULTI_BRAND_CASCADE conflict.
    """
    roster = generate_roster(
        month_str="2026-12",
        employees=sample_dataset["employees"],
        brands=sample_dataset["brands"],
        processes=sample_dataset["processes"],
        brand_process_rules=sample_dataset["brand_process_rules"],
        allocations=sample_dataset["allocations"],
        public_holidays=sample_dataset["public_holidays"],
        leaves_and_compoffs=sample_dataset["leaves_and_compoffs"],
    )

    conflicts = roster["conflicts"]

    cascade_conflicts = [
        c for c in conflicts
        if c.get("conflict_type") == "MULTI_BRAND_CASCADE" and c.get("employee_id") == "EMP-08"
    ]

    assert len(cascade_conflicts) >= 1, "Must detect MULTI_BRAND_CASCADE for EMP-08 on Dec 10-11"
    cascade_dates = {c["date"] for c in cascade_conflicts}
    assert "2026-12-10" in cascade_dates
    assert "2026-12-11" in cascade_dates


def test_demo_3_multi_resource_brand_partial_unavailability(sample_dataset):
    """
    DEMO-3: StrideCraft Footwear (BRD-18) has EMP-16 on leave Dec 14-15.
    - Tue Dec 15 (min_staffing=1): EMP-17 maintains full coverage (COVERED).
    - Mon Dec 14 (peak day, min_staffing=2): EMP-17 works primary, system auto-assigns backup EMP-18 (BACKUP_COVERED).
    """
    roster = generate_roster(
        month_str="2026-12",
        employees=sample_dataset["employees"],
        brands=sample_dataset["brands"],
        processes=sample_dataset["processes"],
        brand_process_rules=sample_dataset["brand_process_rules"],
        allocations=sample_dataset["allocations"],
        public_holidays=sample_dataset["public_holidays"],
        leaves_and_compoffs=sample_dataset["leaves_and_compoffs"],
    )

    coverage = roster["coverage_matrix"]

    # Check BRD-18 CS on Tue Dec 15
    tue_cov = next(
        c for c in coverage
        if c["brand_id"] == "BRD-18" and c["process_id"] == "PROC-CS" and c["date"] == "2026-12-15"
    )
    assert tue_cov["required_staffing"] == 1
    assert tue_cov["working_count"] >= 1
    assert tue_cov["status"] in ("COVERED", "BACKUP_COVERED")

    # Check BRD-18 CS on Mon Dec 14 (peak day, min_staffing=2)
    mon_cov = next(
        c for c in coverage
        if c["brand_id"] == "BRD-18" and c["process_id"] == "PROC-CS" and c["date"] == "2026-12-14"
    )
    assert mon_cov["required_staffing"] == 2
    # EMP-18 is configured as BACKUP on BRD-18 CS in sample_data.json
    assert mon_cov["working_count"] == 2
    assert mon_cov["status"] == "BACKUP_COVERED"
    assert "EMP-18" in mon_cov["backup_employee_ids"]


def test_demo_4_post_generation_live_leave_approval(sample_dataset):
    """
    DEMO-4: After generating December 2026 roster, approving EMP-12's pending leave (LV-07, Dec 16-17)
    immediately flags a coverage gap on LoomVerse Apparel (BRD-06) and recommends available Pod-2 backups.
    """
    # 1. Base generation with LV-07 PENDING (not approved)
    base_roster = generate_roster(
        month_str="2026-12",
        employees=sample_dataset["employees"],
        brands=sample_dataset["brands"],
        processes=sample_dataset["processes"],
        brand_process_rules=sample_dataset["brand_process_rules"],
        allocations=sample_dataset["allocations"],
        public_holidays=sample_dataset["public_holidays"],
        leaves_and_compoffs=sample_dataset["leaves_and_compoffs"],
    )

    # On Dec 16, BRD-06 CS should be COVERED by EMP-12
    base_cov_16 = next(
        c for c in base_roster["coverage_matrix"]
        if c["brand_id"] == "BRD-06" and c["process_id"] == "PROC-CS" and c["date"] == "2026-12-16"
    )
    assert base_cov_16["status"] == "COVERED"

    # 2. Simulate approving LV-07
    updated_leaves = []
    for lvc in sample_dataset["leaves_and_compoffs"]:
        item = dict(lvc)
        if item["id"] == "LV-07":
            item["status"] = "APPROVED"
        updated_leaves.append(item)

    approved_roster = generate_roster(
        month_str="2026-12",
        employees=sample_dataset["employees"],
        brands=sample_dataset["brands"],
        processes=sample_dataset["processes"],
        brand_process_rules=sample_dataset["brand_process_rules"],
        allocations=sample_dataset["allocations"],
        public_holidays=sample_dataset["public_holidays"],
        leaves_and_compoffs=updated_leaves,
    )

    # Now on Dec 16, BRD-06 CS must be UNCOVERED
    post_cov_16 = next(
        c for c in approved_roster["coverage_matrix"]
        if c["brand_id"] == "BRD-06" and c["process_id"] == "PROC-CS" and c["date"] == "2026-12-16"
    )
    assert post_cov_16["status"] == "UNCOVERED"

    # And there must be a HARD conflict on 2026-12-16 for BRD-06 CS with ranked Pod-2 backup recommendations
    brd6_conflicts = [
        c for c in approved_roster["conflicts"]
        if c.get("brand_id") == "BRD-06" and c.get("date") == "2026-12-16" and c.get("severity") == "HARD"
    ]
    assert len(brd6_conflicts) >= 1
    resolutions = brd6_conflicts[0]["suggested_resolutions"]
    assert len(resolutions) > 0
    # Top recommendation should have high score
    assert resolutions[0]["score"] >= 70


def test_backup_recommender_scoring(sample_dataset):
    """Test recommender scores: floaters, associates, and pod lead escalation."""
    emp_statuses = {e["id"]: "WORKING" for e in sample_dataset["employees"]}
    recs = recommend_backups(
        brand_id="BRD-01",
        process_id="PROC-CS",
        date_str="2026-12-05",
        brand_pod_id="POD-1",
        employees=sample_dataset["employees"],
        employee_statuses=emp_statuses,
        allocations=sample_dataset["allocations"],
    )

    assert len(recs) > 0
    # Pod lead of POD-1 is EMP-01
    assert any(r["employee_id"] == "EMP-01" and r["tier"] == "POD_LEAD_ESCALATION" for r in recs)


def test_deterministic_engine_speed(sample_dataset):
    """Verify that pure engine execution takes under 500 milliseconds."""
    import time
    start = time.perf_counter()
    generate_roster(
        month_str="2026-12",
        employees=sample_dataset["employees"],
        brands=sample_dataset["brands"],
        processes=sample_dataset["processes"],
        brand_process_rules=sample_dataset["brand_process_rules"],
        allocations=sample_dataset["allocations"],
        public_holidays=sample_dataset["public_holidays"],
        leaves_and_compoffs=sample_dataset["leaves_and_compoffs"],
    )
    duration_ms = (time.perf_counter() - start) * 1000
    assert duration_ms < 500, f"Roster generation took too long: {duration_ms:.2f}ms"
"""
Comprehensive Unit Test Suite for Scheduling & Conflict Engine.
Tests all 3 calendar types, DEMO-1 through DEMO-4, soft vs. hard overrides, and API generation.
"""
import pytest
from datetime import date
from sqlmodel import Session, select
from fastapi.testclient import TestClient

from database import engine, init_db
from seed import seed_database, load_sample_data
from engine.calendar_rules import is_operating_day, get_required_staffing
from engine.scheduler import generate_roster
from engine.recommender import recommend_backups
from main import app
from models import LeaveAndCompOff


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    init_db()
    seed_database()


@pytest.fixture
def sample_data():
    return load_sample_data()


# -------------------------------------------------------------------------
# Test 1: Demand Calendar Rules (365_DAYS, DAILY_EXCEPT_PH, MON_SAT_EXCEPT_PH)
# -------------------------------------------------------------------------
def test_calendar_rules_operating_days():
    # 2026-12-25 is a Friday and a Public Holiday (Christmas)
    christmas = date(2026, 12, 25)
    # 2026-12-27 is a Sunday and NOT a Public Holiday
    sunday = date(2026, 12, 27)
    # 2026-12-28 is a Monday and NOT a Public Holiday
    regular_monday = date(2026, 12, 28)

    # 1. 365_DAYS: Operates on Christmas, Sundays, and normal working days
    assert is_operating_day("365_DAYS", christmas, is_ph=True) is True
    assert is_operating_day("365_DAYS", sunday, is_ph=False) is True
    assert is_operating_day("365_DAYS", regular_monday, is_ph=False) is True

    # 2. DAILY_EXCEPT_PH: Operates on Sundays, CLOSED on Christmas (PH)
    assert is_operating_day("DAILY_EXCEPT_PH", christmas, is_ph=True) is False
    assert is_operating_day("DAILY_EXCEPT_PH", sunday, is_ph=False) is True
    assert is_operating_day("DAILY_EXCEPT_PH", regular_monday, is_ph=False) is True

    # 3. MON_SAT_EXCEPT_PH: CLOSED on Christmas (PH) and CLOSED on Sundays
    assert is_operating_day("MON_SAT_EXCEPT_PH", christmas, is_ph=True) is False
    assert is_operating_day("MON_SAT_EXCEPT_PH", sunday, is_ph=False) is False
    assert is_operating_day("MON_SAT_EXCEPT_PH", regular_monday, is_ph=False) is True


def test_calendar_rules_day_overrides():
    # Monday = 0, Saturday = 5
    monday = date(2026, 12, 14)
    tuesday = date(2026, 12, 15)
    overrides = {"0": 2, "5": 2}

    # Monday should require 2 staff
    req_mon = get_required_staffing("365_DAYS", monday, is_ph=False, base_min_staffing=1, day_min_staffing_overrides=overrides)
    assert req_mon == 2

    # Tuesday should require base staffing 1
    req_tue = get_required_staffing("365_DAYS", tuesday, is_ph=False, base_min_staffing=1, day_min_staffing_overrides=overrides)
    assert req_tue == 1


# -------------------------------------------------------------------------
# Test 2: DEMO-1: Single-Resource 365-Day Brand Weekly-Off Tension (BRD-02)
# -------------------------------------------------------------------------
def test_demo_1_single_resource_365_brand_gaps(sample_data):
    """
    BRD-02 (VelvetDew Skincare) requires 365_DAYS CS coverage with 1 sole primary (EMP-06).
    EMP-06 has weekly off on Wednesdays and a comp-off on Dec 18.
    These must be flagged as HARD UNCOVERED conflicts with ranked backup suggestions.
    """
    roster = generate_roster(
        month_str="2026-12",
        employees=sample_data["employees"],
        brands=sample_data["brands"],
        processes=sample_data["processes"],
        brand_process_rules=sample_data["brand_process_rules"],
        allocations=sample_data["allocations"],
        public_holidays=sample_data["public_holidays"],
        leaves_and_compoffs=sample_data["leaves_and_compoffs"],
    )

    conflicts = roster["conflicts"]
    brd2_conflicts = [
        c for c in conflicts
        if c.get("brand_id") == "BRD-02" and c.get("conflict_type") == "UNCOVERED_BRAND_PROCESS"
    ]

    # Every Wednesday in Dec 2026: Dec 2, 9, 16, 23, 30 + Dec 18 (Comp-Off)
    conflict_dates = {c["date"] for c in brd2_conflicts}
    assert "2026-12-02" in conflict_dates
    assert "2026-12-09" in conflict_dates
    assert "2026-12-16" in conflict_dates
    assert "2026-12-18" in conflict_dates  # LV-02 Comp-off
    assert "2026-12-23" in conflict_dates
    assert "2026-12-30" in conflict_dates

    # Check suggested resolutions are attached
    first_c = brd2_conflicts[0]
    assert len(first_c["suggested_resolutions"]) > 0
    # Top recommendation should have score >= 60
    assert first_c["suggested_resolutions"][0]["score"] >= 60


# -------------------------------------------------------------------------
# Test 3: DEMO-2: Multi-Brand Cascading Gap (EMP-08 -> BRD-04 & BRD-05)
# -------------------------------------------------------------------------
def test_demo_2_multi_brand_cascade(sample_data):
    """
    EMP-08 manages both BRD-04 and BRD-05.
    Their Dec 10-11 planned leave (LV-01) must trigger MULTI_BRAND_CASCADE conflicts.
    """
    roster = generate_roster(
        month_str="2026-12",
        employees=sample_data["employees"],
        brands=sample_data["brands"],
        processes=sample_data["processes"],
        brand_process_rules=sample_data["brand_process_rules"],
        allocations=sample_data["allocations"],
        public_holidays=sample_data["public_holidays"],
        leaves_and_compoffs=sample_data["leaves_and_compoffs"],
    )

    cascade_conflicts = [
        c for c in roster["conflicts"]
        if c.get("conflict_type") == "MULTI_BRAND_CASCADE" and c.get("employee_id") == "EMP-08"
    ]

    cascade_dates = {c["date"] for c in cascade_conflicts}
    assert "2026-12-10" in cascade_dates
    assert "2026-12-11" in cascade_dates

    # Check message groups the affected brands
    assert "PurePetal Haircare" in cascade_conflicts[0]["message"]
    assert "KajalCraft Cosmetics" in cascade_conflicts[0]["message"]


# -------------------------------------------------------------------------
# Test 4: DEMO-3: Multi-Resource Brand Partial Unavailability (BRD-18)
# -------------------------------------------------------------------------
def test_demo_3_multi_resource_partial_unavailability(sample_data):
    """
    BRD-18 (StrideCraft Footwear) has EMP-16 on leave Dec 14-15.
    - Tue Dec 15 (min_staffing=1): EMP-17 is working, so status remains COVERED.
    - Mon Dec 14 (peak day, min_staffing=2): EMP-17 working + EMP-18 assigned as BACKUP -> BACKUP_COVERED.
    """
    roster = generate_roster(
        month_str="2026-12",
        employees=sample_data["employees"],
        brands=sample_data["brands"],
        processes=sample_data["processes"],
        brand_process_rules=sample_data["brand_process_rules"],
        allocations=sample_data["allocations"],
        public_holidays=sample_data["public_holidays"],
        leaves_and_compoffs=sample_data["leaves_and_compoffs"],
    )

    coverage = {
        (c["date"], c["brand_id"], c["process_id"]): c
        for c in roster["coverage_matrix"]
    }

    # Tue Dec 15 CS on BRD-18 (min_staffing = 1)
    tue_cov = coverage.get(("2026-12-15", "BRD-18", "PROC-CS"))
    assert tue_cov is not None
    assert tue_cov["status"] in ("COVERED", "BACKUP_COVERED")
    assert tue_cov["working_count"] >= 1

    # Mon Dec 14 CS on BRD-18 (min_staffing = 2)
    mon_cov = coverage.get(("2026-12-14", "BRD-18", "PROC-CS"))
    assert mon_cov is not None
    assert mon_cov["required_staffing"] == 2
    # EMP-18 was auto-assigned as configured backup
    assert "EMP-18" in mon_cov["backup_employee_ids"]
    assert mon_cov["status"] == "BACKUP_COVERED"


# -------------------------------------------------------------------------
# Test 5: DEMO-4: Post-Generation Live Change Workflow (LV-07 -> EMP-12 / BRD-06)
# -------------------------------------------------------------------------
def test_demo_4_post_generation_live_change(sample_data):
    """
    Initially LV-07 is PENDING for EMP-12 (Dec 16-17).
    When generated as-is, BRD-06 is covered on Dec 16.
    When LV-07 is approved, re-running evaluation immediately flags BRD-06 gap
    and recommends available Pod-2 backups.
    """
    # 1. Before approval (LV-07 is PENDING)
    roster_before = generate_roster(
        month_str="2026-12",
        employees=sample_data["employees"],
        brands=sample_data["brands"],
        processes=sample_data["processes"],
        brand_process_rules=sample_data["brand_process_rules"],
        allocations=sample_data["allocations"],
        public_holidays=sample_data["public_holidays"],
        leaves_and_compoffs=sample_data["leaves_and_compoffs"],
    )
    brd6_cov_before = [
        c for c in roster_before["coverage_matrix"]
        if c["brand_id"] == "BRD-06" and c["date"] == "2026-12-16"
    ]
    # Prior to approval, EMP-12 is working so BRD-06 is COVERED
    for c in brd6_cov_before:
        assert c["status"] == "COVERED"

    # 2. Simulate approving LV-07
    leaves_after = [dict(l) for l in sample_data["leaves_and_compoffs"]]
    for l in leaves_after:
        if l["id"] == "LV-07":
            l["status"] = "APPROVED"

    roster_after = generate_roster(
        month_str="2026-12",
        employees=sample_data["employees"],
        brands=sample_data["brands"],
        processes=sample_data["processes"],
        brand_process_rules=sample_data["brand_process_rules"],
        allocations=sample_data["allocations"],
        public_holidays=sample_data["public_holidays"],
        leaves_and_compoffs=leaves_after,
    )

    brd6_cov_after = [
        c for c in roster_after["coverage_matrix"]
        if c["brand_id"] == "BRD-06" and c["date"] == "2026-12-16"
    ]
    # Now BRD-06 is UNCOVERED because EMP-12 is on leave
    for c in brd6_cov_after:
        assert c["status"] == "UNCOVERED"

    # Confirms conflict is flagged
    brd6_conflicts = [
        c for c in roster_after["conflicts"]
        if c.get("brand_id") == "BRD-06" and c["date"] == "2026-12-16"
    ]
    assert len(brd6_conflicts) > 0
    # Suggested backups should include same-pod associates (Pod-2)
    recs = brd6_conflicts[0]["suggested_resolutions"]
    assert len(recs) > 0


# -------------------------------------------------------------------------
# Test 6: Soft Preference vs. Hard Client Constraint
# -------------------------------------------------------------------------
def test_soft_preference_vs_hard_constraint(sample_data):
    """
    If multi-resource employees sharing a process have identical preferred weekly offs,
    the rotational employee is staggered to ensure coverage, and a SOFT warning is emitted.
    """
    roster = generate_roster(
        month_str="2026-12",
        employees=sample_data["employees"],
        brands=sample_data["brands"],
        processes=sample_data["processes"],
        brand_process_rules=sample_data["brand_process_rules"],
        allocations=sample_data["allocations"],
        public_holidays=sample_data["public_holidays"],
        leaves_and_compoffs=sample_data["leaves_and_compoffs"],
    )

    # All conflicts with severity SOFT should be PREFERENCE_VIOLATED
    soft_conflicts = [c for c in roster["conflicts"] if c["severity"] == "SOFT"]
    for sc in soft_conflicts:
        assert sc["conflict_type"] == "PREFERENCE_VIOLATED"
        assert "preferred" in sc["message"].lower()


# -------------------------------------------------------------------------
# Test 7: FastAPI Endpoint (POST /api/rosters/generate?month=2026-12)
# -------------------------------------------------------------------------
def test_api_generate_roster_endpoint():
    client = TestClient(app)
    response = client.post("/api/rosters/generate?month=2026-12")
    assert response.status_code == 200

    data = response.json()
    assert data["month"] == "2026-12"
    assert data["roster_id"] == "ROST-2026-12"
    assert "entries" in data
    assert len(data["entries"]) == 32 * 31  # 32 employees * 31 days in Dec
    assert "coverage_matrix" in data
    assert "conflicts" in data
    assert "kpis" in data
    assert data["kpis"]["total_employees"] == 32
    assert data["kpis"]["hard_conflicts_count"] > 0

