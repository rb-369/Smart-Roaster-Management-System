# Smart Roster Management System

> Built for the **Datastraw Tech Internship Assessment Test** (Nov 24 – Nov 28, 2026).
>
> Core Focus: **Reliable deterministic scheduling logic, explicit hard vs. soft conflict detection, and live post-generation change impact**.

---

## 1. Overview & Architecture

The Smart Roster Management System solves the complex multi-client operational scheduling problem for D2C customer experience teams (32 employees across 4 pods, 20 brands, and 5 processes).

### Key Architectural Pillars
1. **Strict Separation of Demand vs. Supply Calendars**:
   - **Demand**: Brand-process rules (`365_DAYS`, `DAILY_EXCEPT_PH`, `MON_SAT_EXCEPT_PH`) with day-of-week minimum staffing overrides.
   - **Supply**: Employee working shifts, weekly offs (fixed or rotational), public holidays, approved leaves, and comp-offs.
2. **Pure Deterministic Scheduling Engine**:
   - Zero LLM or random logic in core scheduling — fast, predictable, reproducible, and verifiable via automated unit tests.
3. **Hard vs. Soft Conflict Detection**:
   - **HARD**: Uncovered brand-processes, understaffed peak days, multi-brand cascading gaps, leave violations, shift overload.
   - **SOFT**: Preferred weekly-off day overridden to maintain mandatory client coverage.
4. **Live Change Impact Analysis**:
   - Post-generation leave approvals or unavailability changes trigger instant incremental re-validation and ranked backup recommendations without wiping unrelated manual adjustments.

---

## 2. Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLModel (SQLAlchemy + Pydantic v2), Pytest
- **Database**: SQLite (local development) / PostgreSQL on Supabase (production)
- **Frontend**: Next.js 14+ (App Router), TypeScript, Tailwind CSS, Lucide Icons
- **Deployment**: Vercel (Frontend), Render / Railway (Backend), Supabase (Database)

---

## 3. Quickstart Guide

### Backend Setup
```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Unix/macOS:
source .venv/bin/activate

pip install -r requirements.txt
python seed.py
pytest -v
uvicorn main:app --reload --port 8000
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

---

## 4. Section 8 Q&A ("Tell Us How You Think")
*(Detailed responses will be finalized in Day 4)*
