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
    """Verify that pure engine execution takes under 150 milliseconds."""
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
    assert duration_ms < 150, f"Roster generation took too long: {duration_ms:.2f}ms"
