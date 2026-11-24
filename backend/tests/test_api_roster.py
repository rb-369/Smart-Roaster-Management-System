from fastapi.testclient import TestClient
from main import app
from database import init_db
from seed import seed_database

client = TestClient(app)


def test_generate_roster_endpoint():
    # Ensure seeded database
    seed_database()
    
    response = client.post("/api/rosters/generate?month=2026-12")
    assert response.status_code == 200, response.text
    data = response.json()
    
    assert data["month"] == "2026-12"
    assert data["roster_id"] == "ROST-2026-12"
    assert "kpis" in data
    assert data["kpis"]["total_employees"] == 32
    assert "entries" in data
    assert len(data["entries"]) > 0
    assert "coverage_matrix" in data
    assert len(data["coverage_matrix"]) > 0
    assert "conflicts" in data
    assert len(data["conflicts"]) > 0
    
    # Check that conflicts include suggested resolutions
    hard_conflicts = [c for c in data["conflicts"] if c["severity"] == "HARD" and c.get("suggested_resolutions")]
    assert len(hard_conflicts) > 0
    first_res = hard_conflicts[0]["suggested_resolutions"][0]
    assert "employee_id" in first_res
    assert "score" in first_res


def test_health_check_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
