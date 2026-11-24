# AGENTS.md — Engineering & Agent Operating Rules

Read `MISSION.md`, `smart_roster_implementation_plan.md`, and `sample_data.json` before making architectural or schema changes.

---

## 1. Tech Stack & Repository Layout

- **Backend**: Python 3.11+, FastAPI, SQLModel (SQLAlchemy + Pydantic), Pytest
- **Database**: SQLite for local dev (`sqlite:///./roster.db`), PostgreSQL (Supabase) in production via `DATABASE_URL`
- **Frontend**: Next.js (App Router), TypeScript (strict), Tailwind CSS, shadcn/ui, Lucide Icons
- **Deployment**: Frontend on Vercel, Backend on Render/Railway, DB on Supabase

```text
/
├── MISSION.md
├── AGENTS.md
├── smart_roster_implementation_plan.md
├── sample_data.json                  # Canonical seed dataset (32 employees, 20 brands)
├── .env.example
├── README.md                         # Must include answers to all 8 Section 8 questions
├── backend/
│   ├── main.py                       # FastAPI app, CORS, router registration
│   ├── database.py                   # Engine, session dependency, init_db
│   ├── models.py                     # 9 core SQLModel tables
│   ├── schemas.py                    # Pydantic request/response DTOs
│   ├── seed.py                       # Idempotent loader for sample_data.json
│   ├── engine/                       # PURE DETERMINISTIC LOGIC (no FastAPI/HTTP imports)
│   │   ├── calendar_rules.py         # Brand-process operating day & min_staffing resolver
│   │   ├── scheduler.py              # Monthly roster generator & staggered off optimizer
│   │   ├── validator.py              # Hard & Soft conflict detector (6 check categories)
│   │   └── recommender.py            # Ranked same-pod/floater/pod-lead backup scorer
│   ├── routers/
│   │   ├── entities.py               # CRUD: pods, processes, employees, brands, rules, allocations
│   │   ├── leaves.py                 # Leaves, comp-offs, holidays, & live approve+impact endpoint
│   │   └── rosters.py                # Generate, 5 views, manual entry patch, assign-backup, CSV export
│   └── tests/
│       └── test_scheduler.py         # Mandatory unit tests for all rules & DEMO-1..DEMO-4
└── frontend/
    ├── src/app/                      # Next.js App Router pages
    ├── src/components/               # RosterMatrix, ConflictDrawer, ViewTabs, CrudModals
    └── src/lib/api.ts                # Typed API client using NEXT_PUBLIC_API_URL
```

---

## 2. Hard Domain Invariants (Never Violate)

1. **Keep the Engine Pure**: Files in `backend/engine/` must NEVER import FastAPI, HTTP request objects, or perform random/LLM calls. They take structured data + `YYYY-MM` and return deterministic outputs so unit tests run in milliseconds.
2. **Separate Demand vs. Supply Calendars**:
   - Demand = `brand_process_rules` (`365_DAYS`, `DAILY_EXCEPT_PH`, `MON_SAT_EXCEPT_PH` + `day_min_staffing_overrides`).
   - Supply = `employees` (`default_weekly_off`, `preferred_weekly_off`, `weekly_off_rule`, `shift`) + `leaves_and_compoffs` + `public_holidays`.
   - Never assume every employee has Sunday off or every brand closes on public holidays.
3. **Weekday Integer Convention**: Always use Python's `date.weekday()` convention everywhere (DB, API, UI): `0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday, 5=Saturday, 6=Sunday`.
4. **Hard vs. Soft Priority**:
   - Hard client coverage (`required_staffing`) ALWAYS takes priority over `preferred_weekly_off`.
   - If a soft preference is overridden to maintain coverage, emit a `SOFT` conflict (`PREFERENCE_VIOLATED`).
   - If coverage still cannot be met, emit a `HARD` conflict (`UNCOVERED_BRAND_PROCESS` or `INSUFFICIENT_STAFFING`) — NEVER silently hide gaps.
5. **Incremental Live Re-Validation**: Manual cell edits (`PATCH /api/rosters/{month}/entry`), leave approvals (`POST /api/leaves/{id}/approve`), and 1-click backup assignments (`POST /api/rosters/{month}/assign-backup`) MUST re-run `validator.py` immediately and return the updated coverage & conflicts without wiping unrelated manual overrides.
6. **Zero Hardcoded Mock Data in Frontend**: All UI views, KPIs, and dropdowns must read live from the FastAPI backend. Keep `sample_data.json` as the single source of truth via `seed.py`.
7. **Schema Integrity**: Do not rename fields in `sample_data.json` without simultaneously updating `backend/models.py`, `backend/seed.py`, and `backend/tests/test_scheduler.py`.

---

## 3. Standard Commands

### Backend
```bash
# Setup
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Seed database from ../sample_data.json
python seed.py

# Run test suite (MUST pass before finishing any backend task)
pytest -v

# Start dev server
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
# Setup & dev
cd frontend
npm install
npm run dev

# Verification (MUST pass before finishing any frontend task)
npm run lint
npm run build
```

---

## 4. API & UI Implementation Rules

- **Consistent View Endpoint**: `GET /api/rosters/{month}?view=company|pod|brand|process|employee&filter_id=...` should return both `entries`, `coverage_summary`, and `conflicts` so all 5 stakeholder views share one reliable source of truth.
- **Readable Conflict Payloads**: Every conflict object must include `severity` (`HARD` | `SOFT`), `conflict_type`, `date`, `brand_id`, `process_id`, `employee_id`, a plain-English `message` explaining *why* it occurred, and `suggested_resolutions[]` (top 3 ranked backups with scores and reasons).
- **Compact Status Codes in Roster Grid**:
  - `W` = Working (green/neutral)
  - `WO` = Weekly Off (slate)
  - `PH` = Public Holiday (blue)
  - `LV` = Planned Leave (amber)
  - `CO` = Comp-Off (purple)
  - `BK` = Backup Coverage (teal)
- **Coverage Badges on Brand/Process Rows**:
  - `COVERED` (green, e.g. `1/1` or `2/2`)
  - `BACKUP_COVERED` (teal, e.g. `1/1 BK`)
  - `UNDERSTAFFED` (amber/red, e.g. `1/2 SHORT`)
  - `UNCOVERED` (red, e.g. `0/1 GAP`)
  - `NOT_OPERATING` (muted gray, `—`)

---

## 5. Verification Checklist Before Marking Any Task Done

1. **After any engine or API edit**: Run `pytest -v` in `/backend` and verify all tests pass, specifically checking `DEMO-1`, `DEMO-2`, `DEMO-3`, and `DEMO-4`.
2. **After any frontend edit**: Run `npm run build` in `/frontend` to confirm zero TypeScript or Next.js build errors.
3. **Before deployment**:
   - Confirm `.env.example` documents `DATABASE_URL` and `NEXT_PUBLIC_API_URL` (never commit real secrets or `.env`).
   - Confirm `POST /api/admin/reset-seed` restores a clean `2026-12` demo state without errors.
   - Verify CORS allows the deployed Vercel origin.
