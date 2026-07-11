# Dashboard Gerencial Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a protected manager/owner dashboard at `/admin/dashboard` backed by a protected summary endpoint.

**Architecture:** Add a backend summary helper and `GET /api/admin/dashboard-summary` guarded by `require_admin_user`. Add a small frontend service for dashboard data and a new Vue view that reuses the current admin-route guard, Tailwind style, and local sync store for device-local pending records.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic-style dict responses, Vue 3, Vue Router, Pinia, Tailwind, Node test runner, pytest.

---

### Task 1: Backend Admin Summary

**Files:**
- Modify: `backend/main.py`
- Test: `backend/test_admin_dashboard.py`

- [ ] **Step 1: Write failing backend tests**

Create `backend/test_admin_dashboard.py` with tests that insert minimal records, override the current user dependency, call `/api/admin/dashboard-summary`, and assert admin access plus numeric KPIs.

- [ ] **Step 2: Run test to verify it fails**

Run: `O:\envs\registro_viajes\Scripts\python.exe -m pytest backend\test_admin_dashboard.py -q`

Expected: FAIL because `/api/admin/dashboard-summary` does not exist.

- [ ] **Step 3: Implement backend helper and route**

In `backend/main.py`, add a focused `build_admin_dashboard_summary(db, fecha_desde, fecha_hasta)` helper and `@api_router.get("/admin/dashboard-summary")` route guarded by `require_admin_user`.

- [ ] **Step 4: Run backend test**

Run: `O:\envs\registro_viajes\Scripts\python.exe -m pytest backend\test_admin_dashboard.py -q`

Expected: PASS.

### Task 2: Frontend Admin Route and Service

**Files:**
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/views/Settings.vue`
- Create: `frontend/src/services/adminDashboard.js`
- Test: `frontend/tests/adminDashboard.test.js`
- Modify: `frontend/tests/authGuard.test.js`

- [ ] **Step 1: Write failing frontend tests**

Add tests for default monthly range, API URL construction, response normalization, and `/admin/dashboard` requiring admin.

- [ ] **Step 2: Run test to verify it fails**

Run: `Push-Location frontend; npm run test -- tests/adminDashboard.test.js tests/authGuard.test.js; Pop-Location`

Expected: FAIL because `adminDashboard.js` and the route do not exist.

- [ ] **Step 3: Implement route, service, and settings link**

Add `/admin/dashboard` with `requiresAdmin`, create helpers in `adminDashboard.js`, and add a settings button for authorized users.

- [ ] **Step 4: Run frontend tests**

Run: `Push-Location frontend; npm run test -- tests/adminDashboard.test.js tests/authGuard.test.js; Pop-Location`

Expected: PASS.

### Task 3: Frontend Admin Dashboard View

**Files:**
- Create: `frontend/src/views/AdminDashboard.vue`
- Modify: `frontend/src/router/index.js`

- [ ] **Step 1: Implement Vue view**

Create the protected dashboard screen with date filters, executive KPI cards, rankings, alerts, local pending counts, refresh action, and link to `/admin/logs`.

- [ ] **Step 2: Run frontend verification**

Run: `Push-Location frontend; npm run test; npm run build; Pop-Location`

Expected: all tests and build pass.

### Task 4: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run backend verification**

Run: `O:\envs\registro_viajes\Scripts\python.exe -m py_compile backend\main.py backend\models.py backend\schemas.py backend\database.py backend\logger.py backend\email_service.py backend\scheduler.py`

Run: `Push-Location backend; O:\envs\registro_viajes\Scripts\python.exe -m pytest -q; Pop-Location`

- [ ] **Step 2: Run frontend verification**

Run: `Push-Location frontend; npm run verify; Pop-Location`

- [ ] **Step 3: Review diff**

Run: `git diff -- web/registro_viajes/backend web/registro_viajes/frontend web/registro_viajes/docs/superpowers/plans`

Confirm only dashboard-related files changed.
