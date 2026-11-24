import json
import os
from pathlib import Path
from sqlmodel import Session, delete
from database import engine, init_db
from models import (
    Pod,
    Process,
    Employee,
    Brand,
    BrandProcessRule,
    Allocation,
    PublicHoliday,
    LeaveAndCompOff,
    Roster,
    RosterEntry,
    RosterConflict,
)


def load_sample_data(filepath: str | None = None) -> dict:
    if filepath is None:
        candidates = [
            Path("sample_data.json"),
            Path("../sample_data.json"),
            Path(__file__).parent.parent / "sample_data.json",
            Path(__file__).parent / "sample_data.json",
        ]
        for p in candidates:
            if p.exists():
                filepath = str(p.resolve())
                break
    if not filepath or not os.path.exists(filepath):
        raise FileNotFoundError(f"sample_data.json could not be found.")

    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def seed_database(data: dict | None = None):
    init_db()
    if data is None:
        data = load_sample_data()

    with Session(engine) as session:
        # Clear existing data in reverse dependency order
        session.exec(delete(RosterConflict))
        session.exec(delete(RosterEntry))
        session.exec(delete(Roster))
        session.exec(delete(LeaveAndCompOff))
        session.exec(delete(PublicHoliday))
        session.exec(delete(Allocation))
        session.exec(delete(BrandProcessRule))
        session.exec(delete(Brand))
        session.exec(delete(Employee))
        session.exec(delete(Pod))
        session.exec(delete(Process))
        session.commit()

        # 1. Processes
        for proc in data.get("processes", []):
            session.add(Process(**proc))
        session.commit()

        # 2. Pods
        for pod in data.get("pods", []):
            session.add(Pod(**pod))
        session.commit()

        # 3. Employees
        for emp in data.get("employees", []):
            session.add(Employee(**emp))
        session.commit()

        # 4. Brands
        for brd in data.get("brands", []):
            session.add(Brand(**brd))
        session.commit()

        # 5. Brand Process Rules
        for bpr in data.get("brand_process_rules", []):
            session.add(BrandProcessRule(**bpr))
        session.commit()

        # 6. Allocations
        for alc in data.get("allocations", []):
            session.add(Allocation(**alc))
        session.commit()

        # 7. Public Holidays
        for ph in data.get("public_holidays", []):
            session.add(PublicHoliday(**ph))
        session.commit()

        # 8. Leaves and Comp-offs
        for lvc in data.get("leaves_and_compoffs", []):
            session.add(LeaveAndCompOff(**lvc))
        session.commit()

    print(f"Successfully seeded database:")
    print(f"  - {len(data.get('processes', []))} processes")
    print(f"  - {len(data.get('pods', []))} pods")
    print(f"  - {len(data.get('employees', []))} employees")
    print(f"  - {len(data.get('brands', []))} brands")
    print(f"  - {len(data.get('brand_process_rules', []))} brand process rules")
    print(f"  - {len(data.get('allocations', []))} allocations")
    print(f"  - {len(data.get('public_holidays', []))} public holidays")
    print(f"  - {len(data.get('leaves_and_compoffs', []))} leaves & comp-offs")


if __name__ == "__main__":
    seed_database()
