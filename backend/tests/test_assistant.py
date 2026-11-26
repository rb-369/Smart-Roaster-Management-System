"""
Tests for Read-Only Roster Copilot (/api/assistant/chat).
"""
import httpx
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from database import engine
from main import app
from models import Employee, LeaveAndCompOff, Roster, RosterConflict, RosterEntry
from seed import seed_database

client = TestClient(app)


def _snapshot_db_counts() -> dict:
    with Session(engine) as session:
        return {
            "rosters": len(session.exec(select(Roster)).all()),
            "entries": len(session.exec(select(RosterEntry)).all()),
            "conflicts": len(session.exec(select(RosterConflict)).all()),
            "employees": len(session.exec(select(Employee)).all()),
            "leaves": len(session.exec(select(LeaveAndCompOff)).all()),
        }


def test_assistant_chat_deterministic_fallback_and_read_only(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    seed_database()

    # Ensure 2026-12 roster exists cleanly
    gen_res = client.post("/api/rosters/generate?month=2026-12")
    assert gen_res.status_code == 200

    counts_before = _snapshot_db_counts()

    # 1. Dec 25 (Christmas) query
    res_xmas = client.post(
        "/api/assistant/chat",
        json={
            "month": "2026-12",
            "message": "Which brands have gaps on Dec 25 (Christmas)?",
            "history": [],
        },
    )
    assert res_xmas.status_code == 200
    body_xmas = res_xmas.json()
    assert body_xmas["month"] == "2026-12"
    assert body_xmas["source"] == "deterministic_fallback"
    assert "2026-12-25" in body_xmas["reply"]
    assert "365_DAYS" in body_xmas["reply"]

    # 2. Kabir Verma Dec 10-11 query
    res_kabir = client.post(
        "/api/assistant/chat",
        json={
            "month": "2026-12",
            "message": "Who can cover for Kabir Verma on Dec 10–11?",
            "history": [],
        },
    )
    assert res_kabir.status_code == 200
    body_kabir = res_kabir.json()
    assert body_kabir["source"] == "deterministic_fallback"
    assert "EMP-08" in body_kabir["reply"]
    assert "BRD-04" in body_kabir["reply"]
    assert "Score" in body_kabir["reply"]

    # 3. Pod 1 bottleneck query
    res_pod = client.post(
        "/api/assistant/chat",
        json={
            "month": "2026-12",
            "message": "Why does Pod 1 have the most conflicts this month?",
            "history": [],
        },
    )
    assert res_pod.status_code == 200
    body_pod = res_pod.json()
    assert body_pod["source"] == "deterministic_fallback"
    assert "POD-1" in body_pod["reply"]

    # 4. Sunday-off fairness query
    res_sun = client.post(
        "/api/assistant/chat",
        json={
            "month": "2026-12",
            "message": "Which employees have the fewest Sunday offs?",
            "history": [],
        },
    )
    assert res_sun.status_code == 200
    body_sun = res_sun.json()
    assert body_sun["source"] == "deterministic_fallback"
    assert "Sunday" in body_sun["reply"]
    assert "EMP-" in body_sun["reply"]

    # 5. First-name employee holiday query (e.g. "when does Omkar have holiday?")
    res_emp = client.post(
        "/api/assistant/chat",
        json={
            "month": "2026-12",
            "message": "when does Omkar have holiday?",
            "history": [],
        },
    )
    assert res_emp.status_code == 200
    body_emp = res_emp.json()
    assert body_emp["source"] == "deterministic_fallback"
    assert "Omkar" in body_emp["reply"]
    assert "Weekly Off Dates" in body_emp["reply"]

    # 6. General overview should report real total_operating_slots (never /0 slots)
    res_ov = client.post(
        "/api/assistant/chat",
        json={
            "month": "2026-12",
            "message": "Give me a coverage summary",
            "history": [],
        },
    )
    assert res_ov.status_code == 200
    assert "/0 slots" not in res_ov.json()["reply"]

    # Strictly read-only: DB row counts must be unchanged
    counts_after = _snapshot_db_counts()
    assert counts_after == counts_before


def test_assistant_chat_falls_back_on_openrouter_timeout(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    async def fake_post(*args, **kwargs):
        raise httpx.TimeoutException("Simulated timeout")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    res = client.post(
        "/api/assistant/chat",
        json={
            "month": "2026-12",
            "message": "Which employees have the fewest Sunday offs?",
            "history": [{"role": "user", "content": "Hi"}],
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["source"] == "deterministic_fallback"
    assert "EMP-" in data["reply"]
