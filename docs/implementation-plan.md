# CareerPilot — Implementation Plan

## 0. Environment snapshot (verified on this machine, 2026-10-25)

| Tool | Version | Status |
|---|---|---|
| Python | 3.11.9 | Pre-installed |
| Node.js | 24.22.1 | Installed this session via `winget` |
| npm | 11.19.1 | Installed alongside Node.js |
| Git | 2.55.0.windows.1 | Pre-installed |
| PostgreSQL | 17.11 | Installed this session via `winget`, running as Windows service `postgresql-x64-17` |
| Docker Desktop | — | **Not installed** (user chose to skip for now). `docker-compose.yml` is written for later/CI parity, but Phase 1 local dev runs against the native PostgreSQL service above. |

Databases created: `careerpilot_dev` and `careerpilot_test`, owned by role `careerpilot`.
Credentials live only in `backend/.env` (gitignored) — see README for exact values used locally.

## 1. Phase definitions

- **Phase 1 (this effort)**: everything listed in the user's "FOR PHASE 1" section — repo
  scaffolding, FastAPI backend, React/TS frontend, Postgres + Alembic, candidate profile +
  preferences, Greenhouse/Lever/Ashby adapters behind a configurable registry, discovery +
  normalization + dedup, rule-based eligibility/scoring, saved/dismissed states, a dashboard on
  real data, manual trigger + basic scheduling, tests, and Windows setup docs.
- **Phase 2+ (not started)**: resume tailoring, AI provider management, answer library, form
  automation, submission authorization engine, application queue/state machine, tracker,
  analytics/notifications, full audit logging. These are designed for (see `docs/data-model.md`
  §5 and `docs/architecture.md` §8) but zero code is written for them in Phase 1, and autonomous
  submission remains impossible because no submission code path exists yet.

## 2. Phase 1 increments (checklist)

Each increment is implemented, tested, and reported on before moving to the next. Status is kept
current here and in the session's TODO list.

- [x] **0. Tool verification** — confirmed Python/Node/npm/Git/PostgreSQL as above.
- [x] **1. Planning docs** — `docs/architecture.md`, `docs/data-model.md`, `docs/implementation-plan.md`.
- [x] **2. Repo scaffolding** — `backend/`, `frontend/`, `.gitignore`, top-level `README.md`.
- [x] **3. Backend skeleton** — FastAPI app factory (`lifespan` context manager), settings
      (Pydantic `BaseSettings` reading `.env`), structured JSON logging, `/health` endpoint
      (liveness + DB connectivity), DB session wiring. Verified with a live `uvicorn` run +
      `Invoke-RestMethod` hitting `/health` → `{status: ok, database: ok}`.
- [x] **4. SQLAlchemy models + Alembic** — all 13 Phase 1 tables from `docs/data-model.md`, one
      migration generated and applied to `careerpilot_dev` **and** `careerpilot_test`. Required a
      regeneration after discovering SQLAlchemy's default `Enum()` stores member *names* rather
      than the `.value` strings Postgres' native enums expect (`pg_enum()` helper in
      `app/models/base.py` fixes this).
- [x] **5. Candidate profile + preferences API** — CRUD endpoints, Pydantic schemas, service
      layer, unit + integration tests against the real test DB.
- [x] **6. Job source registry** — `employers`/`job_sources` CRUD (create/list/enable/disable),
      `backend/scripts/seed_job_sources.py` seeds 5 real, verified-reachable public boards
      (Stripe/Greenhouse, Palantir/Lever, OpenAI+Notion+Ramp/Ashby).
- [x] **7. Greenhouse adapter, end to end** — HTTP client → normalization → dedup → persistence →
      `discovery_run` bookkeeping, with unit tests (fixtures matching real verified API shapes)
      and an integration test proving rows land in Postgres.
- [x] **8. Lever adapter** — same pattern as Greenhouse, reusing shared normalization/dedup code.
- [x] **9. Ashby adapter** — same pattern. Live discovery against OpenAI's real Ashby board
      surfaced a genuine production bug (duplicate location strings across `location` and
      `secondaryLocations` violating a unique constraint), fixed in
      `discovery_service._dedupe_preserving_order()` with a regression test.
- [x] **10. Eligibility + match scoring** — rule-based, fully explainable service
      (`eligibility_service.py`), persisted `job_assessments` with reason lists, unit tests
      covering eligible/ineligible/unknown branches for both sponsorship and graduation timing.
- [x] **11. Saved/dismissed endpoints** — `job_candidate_states` CRUD via `PATCH
      /api/jobs/{id}/state`, tests.
- [x] **12. Discovery orchestration** — manual trigger endpoint (`POST /api/discovery/runs`),
      APScheduler-based periodic job reusing the exact same service call, `GET
      /api/discovery/runs/latest` and `/scheduler-status` for the dashboard.
- [x] **13. Frontend scaffold** — Vite + React 19 + TypeScript + Tailwind v4, typed API client
      (`frontend/src/api/`), single-page dashboard layout, accessible components (semantic HTML,
      labeled form controls, visible focus rings, `aria-pressed`/`aria-expanded` on interactive
      elements).
- [x] **14. Dashboard wired to real data** — profile summary + editor, preferences editor
      (locations/roles/employment types/start window/min score), job list with state filters,
      save/dismiss/unsave actions, "Run discovery now" button, discovery run status panel,
      scheduler status display. Explicit loading/empty/error states on every data-fetching
      component (`useFetch` hook + `StatusViews`). No hardcoded job data anywhere — verified by
      browser automation (Playwright) driving real create-profile, save-preferences, and
      save-job flows end to end against the live backend, then confirming via direct API calls
      that the data actually persisted to Postgres.
- [x] **15. Docker Compose** — `docker-compose.yml` + `backend/Dockerfile` +
      `frontend/Dockerfile` written for later convenience/CI parity. **Not exercised end-to-end**
      — Docker Desktop isn't installed on this dev machine (see §0), so this path is unverified
      and should be run through CI or a Docker-capable machine before being relied on. The
      verified Phase 1 workflow is native Postgres + venv + npm (steps 1–3 in `README.md`).
- [x] **16. Full test pass** — `pytest -q` in `backend/`: **92 passed**, 0 failed. Frontend:
      `tsc -b --noEmit` and `npm run build` both clean (no type errors, no bundler errors).
- [x] **17. README** — `README.md` at the repo root with the exact PowerShell commands run on
      this machine (database role/db creation, venv, `alembic upgrade head`, seed script,
      `uvicorn`, `npm install`/`npm run dev`, `pytest`, `npm run build`).

## 3. Working agreements for this project

- Every increment above ends with: a list of changed/added files, the exact commands run to test
  it, and the exact output (trimmed if long, but not misrepresented).
- No increment is marked done until its tests actually pass against the real `careerpilot_test`
  Postgres database (for anything touching the DB) or real `uvicorn`/`vite` processes (for
  anything touching HTTP).
- If a public job board endpoint is unreachable or changes shape, that will be stated plainly,
  and tests will fall back to recorded fixtures rather than silently skipping coverage.
- No dependency is added to `requirements.txt`/`package.json` without being used in the same
  increment that adds it.
- Autonomous submission code is explicitly out of scope until Phase 1's non-negotiables are
  re-confirmed with the user and a dedicated phase is scoped for it.

## 4. Immediate next step

All 17 Phase 1 increments above are complete and verified (92/92 backend tests passing, frontend
type-checks and builds cleanly, and the dashboard was driven end-to-end through real create/save
flows with persistence confirmed directly against Postgres). Phase 1 is done.

Per the user's explicit instruction, Phase 2 (resume tailoring, AI provider management, answer
library, form automation, submission authorization engine, application queue/state machine,
tracker, analytics, full audit logging — and eventually, only within configured standing
authorization and after end-to-end testing, autonomous submission) has **not** been started and
should not begin without further direction, since no Phase 2 code exists yet and none of its
specific safety requirements have been implemented or tested.
