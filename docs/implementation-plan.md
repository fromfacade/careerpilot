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
- [ ] **2. Repo scaffolding** — `backend/`, `frontend/`, `.gitignore`, top-level `README.md` stub.
- [ ] **3. Backend skeleton** — FastAPI app factory, settings (Pydantic `BaseSettings` reading
      `.env`), structured logging, `/health` endpoint, DB session wiring. Verified with a live
      `uvicorn` run + `curl`/`Invoke-RestMethod` hitting `/health`.
- [ ] **4. SQLAlchemy models + Alembic** — all Phase 1 tables from `docs/data-model.md`, first
      migration generated and applied to `careerpilot_dev` **and** `careerpilot_test`, verified
      with `psql \dt` and `alembic current`.
- [ ] **5. Candidate profile + preferences API** — CRUD endpoints, Pydantic schemas, service
      layer, unit + integration tests against the real test DB.
- [ ] **6. Job source registry** — `employers`/`job_sources` CRUD (at least create/list/enable),
      seed config for a small number of real public boards.
- [ ] **7. Greenhouse adapter, end to end** — HTTP client → normalization → dedup → persistence →
      `discovery_run` bookkeeping, with unit tests (fixtures) and one integration test proving
      rows land in Postgres. This is the pattern the other two adapters copy.
- [ ] **8. Lever adapter** — same pattern as Greenhouse, reusing shared normalization/dedup code.
- [ ] **9. Ashby adapter** — same pattern.
- [ ] **10. Eligibility + match scoring** — rule-based service, persisted `job_assessments`,
      explicit reasons, unit tests covering eligible/ineligible/unknown branches.
- [ ] **11. Saved/dismissed endpoints** — `job_candidate_states` CRUD, tests.
- [ ] **12. Discovery orchestration** — manual trigger endpoint, APScheduler-based periodic job
      reusing the same service call, run-status endpoint for the dashboard.
- [ ] **13. Frontend scaffold** — Vite + React + TS + Tailwind, typed API client, routing (even
      if single-page), base layout, accessible components (semantic HTML, labeled form controls,
      focus-visible styles, color contrast).
- [ ] **14. Dashboard wired to real data** — profile summary, preferences editor, job list with
      filters, save/dismiss actions, "Run discovery" button, discovery run status panel. Explicit
      loading/empty/error states for every data-fetching view. No hardcoded job data; fixtures
      only under an explicit `VITE_DEMO_MODE`/test flag.
- [ ] **15. Docker Compose** — Postgres + backend + frontend services, for later convenience/CI;
      not required for local Phase 1 dev given native Postgres is already running.
- [ ] **16. Full test pass** — `pytest` (backend) and frontend type-check/build green; results
      reported verbatim, not summarized as "works."
- [ ] **17. README** — exact PowerShell commands to set up and run everything locally, matching
      what was actually run on this machine (not generic/platform-agnostic boilerplate).

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

Proceed to increment 2 (repo scaffolding) followed by increment 3 (backend skeleton with a real
`/health` check), per the plan above.
