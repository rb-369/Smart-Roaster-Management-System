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
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
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

    # 5. First-name employee holiday query
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

    # 5b. Specific assignment query
    res_assign = client.post(
        "/api/assistant/chat",
        json={
            "month": "2026-12",
            "message": "Which company is @Omkar Bhosale (EMP-30) assigned to?",
            "history": [],
        },
    )
    assert res_assign.status_code == 200
    body_assign = res_assign.json()
    assert "EMP-30" in body_assign["reply"]
    assert "Primary Assignments" in body_assign["reply"]
    assert "Weekly Off Dates" not in body_assign["reply"]

    # 5c. Ordinal date assignment query ("on 17th December")
    res_where = client.post(
        "/api/assistant/chat",
        json={
            "month": "2026-12",
            "message": "Where can I assign @Omkar Bhosale (EMP-30) on 17th December?",
            "history": [],
        },
    )
    assert res_where.status_code == 200
    body_where = res_where.json()
    assert "2026-12-17" in body_where["reply"]
    assert "WEEKLY_OFF" in body_where["reply"]

    # 6. General overview reports real total_operating_slots
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


def test_assistant_chat_ai_tool_calling_loop(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    call_count = {"n": 0}

    class FakeResp:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    async def fake_post(self, url, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return FakeResp({
                "candidates": [{
                    "content": {
                        "role": "model",
                        "parts": [{
                            "functionCall": {
                                "name": "get_employee_details",
                                "args": {"employee_query": "EMP-30", "date": "2026-12-17"},
                            }
                        }],
                    }
                }]
            })
        # Verify tool response was fed back to the model
        contents = kwargs["json"]["contents"]
        tool_resp = contents[-1]["parts"][0]["functionResponse"]["response"]["result"]
        assert tool_resp["employee"]["id"] == "EMP-30"
        assert tool_resp["date_check"]["date"] == "2026-12-17"
        return FakeResp({
            "candidates": [{
                "content": {
                    "role": "model",
                    "parts": [{"text": "Omkar Bhosale (EMP-30) is on WEEKLY_OFF on 2026-12-17; swap his off to cover open POD-4 gaps."}],
                }
            }]
        })

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    res = client.post(
        "/api/assistant/chat",
        json={
            "month": "2026-12",
            "message": "Where can I assign @Omkar Bhosale (EMP-30) on 17th December?",
            "history": [],
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["source"] == "ai"
    assert "Gemini" in (data.get("provider") or "")
    assert "EMP-30" in data["reply"]
    assert call_count["n"] == 2


def test_assistant_chat_falls_back_on_provider_timeout(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

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
