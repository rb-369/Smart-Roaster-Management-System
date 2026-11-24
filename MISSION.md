# MISSION.md — Smart Roster Management System

## 1. North Star Objective
Build and publicly deploy a working **Smart Roster Management System** for the **Datastraw Tech Internship Assessment Test** within **4 days** (Nov 24 – Nov 28, 2026).

> **Core Principle (Assessment Section 10)**:  
> A tool with **reliable deterministic scheduling logic** and **clear conflict detection** is strictly more valuable than a visually impressive interface that generates invalid rosters. Solve the operational scheduling problem first.

---

## 2. The Operational Problem We Are Solving
A D2C customer experience and operations company manages **32 employees** across **4 pods**, **20 D2C brands**, and **5 processes** (`CS`, `ACC`, `Retention`, `NDR`, `Escalations`):
- **80% Single-Resource Brands (16/20)**: One dedicated employee handles all processes for the brand.
- **20% Multi-Resource Brands (4/20)**: 2–3 employees handle separate processes, shared/overlapping processes, or peak days requiring `min_staffing >= 2`.
- **Two Separate Calendars**: Every `(brand, process)` has its own **Operating Calendar** (`365_DAYS`, `DAILY_EXCEPT_PH`, or `MON_SAT_EXCEPT_PH`) and daily `min_staffing`, completely separate from each **Employee's Working Schedule** (weekly offs, public holidays, planned leaves, comp-offs, shifts).
- **Cascading Impact**: One employee may span multiple brands (`EMP-08` owns `BRD-04` and `BRD-05`), so a single leave or weekly-off change can create simultaneous coverage gaps across multiple accounts.

---

## 3. Non-Negotiable Acceptance Criteria

### Core Functional Requirements
- [ ] **Central Database & CRUD (3A)**: Full UI + API CRUD for Employees, Pods, Pod Leads, Brands, Processes, Operating Rules, Allocations, Public Holidays, and Leaves/Comp-Offs — zero code changes needed to add/edit assignments.
- [ ] **Client-Specific Operating Rules (3B)**: Support `365_DAYS`, `DAILY_EXCEPT_PH`, `MON_SAT_EXCEPT_PH`, per-process rules within the same brand, and day-of-week `min_staffing` overrides.
- [ ] **Deterministic Monthly Roster Generation (3C)**: Generate a full monthly roster (default `2026-12`) showing daily employee statuses and daily `(brand, process)` coverage statuses (`COVERED`, `BACKUP_COVERED`, `UNDERSTAFFED`, `UNCOVERED`, `NOT_OPERATING`). Never silently produce an invalid roster.
- [ ] **Hard vs. Soft Conflict Detection (3D)**: Explicitly detect and explain:
  - Uncovered brand/process on a required operating day (**HARD**)
  - Insufficient staffing (`working < min_staffing`) (**HARD**)
  - Multi-brand cascading gap from one employee's absence (**HARD**)
  - Approved leave/comp-off or weekly-off rule violations (**HARD**)
  - Overlapping/incompatible shifts or manual overload (**HARD**)
  - Preferred weekly-off overridden to protect client coverage (**SOFT**)
- [ ] **5 Stakeholder Views + Manual Editing (3E)**: Company-wide, Pod-wise, Brand-wise, Process-wise, and Employee-wise views. Clicking any cell allows manual override with immediate live re-validation.
- [ ] **Post-Generation Change Handling (3F)**: Handle availability/leave changes after generation without rebuilding the entire month, evaluating whether remaining team members maintain coverage and recommending ranked same-pod backups.

### Required Demo Scenarios (Must Work End-to-End with `sample_data.json`)
1. **`DEMO-1` (`BRD-02` VelvetDew Skincare)**: Single-resource `365_DAYS` CS brand flags hard coverage gaps on `EMP-06`'s weekly offs and Dec 18 comp-off.
2. **`DEMO-2` (`EMP-08` → `BRD-04` + `BRD-05`)**: Single employee's Dec 10–11 planned leave flags a grouped multi-brand cascade across 2 brands and 4 processes.
3. **`DEMO-3` (`BRD-18` StrideCraft Footwear)**: When `EMP-16` is on leave Dec 14–15, Tue Dec 15 (`min_staffing=1`) stays **COVERED** by `EMP-17`, while peak Mon Dec 14 (`min_staffing=2`) activates backup `EMP-18` or flags insufficient staffing.
4. **`DEMO-4` (`LV-07` → `EMP-12` / `BRD-06`)**: Approving pending leave `LV-07` (Dec 16–17) *after* roster generation immediately flags the `BRD-06` gap and offers 1-click backup assignment.

---

## 4. High-ROI Extras (Build ONLY After Core Passes)
1. **Ranked Backup Recommendations** (1-click resolution inside Conflict Drawer).
2. **CSV Roster Export** (`GET /api/rosters/{month}/export.csv`).
3. **Reset Demo Data Button** (idempotent re-seed from `sample_data.json` for evaluators).
4. **Weekly-Off Fairness Summary** (counts per employee in Employee-wise view).

### Explicit Non-Goals (Do Not Build)
- Do **not** build complex login/RBAC walls that block evaluators from testing the public URL immediately.
- Do **not** use an LLM to generate or validate rosters (all scheduling and conflict logic must be 100% deterministic Python).
- Do **not** spend time on decorative animations, dark/light theme toggles, or analytics charts before all 4 demo scenarios and unit tests pass.

---

## 5. 4-Day Milestone Gates
- **Day 1 Gate**: Monorepo scaffolded, 9-table DB + `seed.py` loading `sample_data.json`, pure deterministic engine (`scheduler.py`, `validator.py`, `recommender.py`), and passing `pytest` suite covering all 4 demo scenarios.
- **Day 2 Gate**: Full FastAPI REST API + live incremental re-validation endpoints + Next.js CRUD management tabs working against the backend.
- **Day 3 Gate**: All 5 roster views + interactive cell override popover + Hard/Soft Conflict Drawer + 1-click `DEMO-4` pending leave approval & backup assignment.
- **Day 4 Gate**: Live public deployment (Vercel + Render/Railway + Supabase PostgreSQL), `README.md` answering all 8 Section 8 questions, `.env.example`, 3–5 min demo video, and submission email sent.
