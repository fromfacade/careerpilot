# CareerPilot — Architecture

## 1. Purpose and scope

CareerPilot is a local-first, autonomous job-search and application assistant. It discovers
technical job postings, evaluates whether the candidate (Luis Castellanos, UCSC CS, expected
graduation Dec 2027) is eligible and how well a posting matches configured preferences, tailors
resumes, and — in later phases, under strict human-configured authorization — prepares and
submits applications.

This document describes the target architecture across all 15 planned modules, but is explicit
about **what exists today (Phase 1)** versus **what is designed-for-but-not-built**. Phase 1
intentionally stops before any resume generation, AI provider calls, answer libraries, form
automation, or submission logic — see `docs/implementation-plan.md` for the phase breakdown.

## 2. Guiding engineering principles

- **Clean service boundaries.** Each module is a Python package under `backend/app/` with a
  narrow public interface (typed functions/classes in `service.py`). Modules talk to each other
  through services, never by reaching into each other's ORM queries or private helpers.
- **External I/O is isolated.** Anything that talks to the outside world (Greenhouse/Lever/Ashby
  HTTP APIs, future AI providers, future form automation) lives behind an adapter/client class in
  a `clients/` or `adapters/` subpackage, with a typed interface. Business logic depends on the
  interface, not the HTTP client, so it can be tested with fakes/mocks.
- **Untrusted input discipline.** Job descriptions, titles, and any other third-party content are
  treated as untrusted strings: they are never executed, rendered as HTML without sanitization,
  or interpolated into shell/SQL commands. Normalization strips/escapes content before storage
  and the frontend renders job descriptions as plain text (no `dangerouslySetInnerHTML`).
  Outbound HTTP calls to job boards use allow-listed, configured hosts only.
- **Explicit unknowns.** Nullable booleans are avoided for safety-relevant fields (work
  authorization, sponsorship requirement, eligibility, remote type). We use enums with an
  explicit `unknown` member so "we don't know yet" is never silently treated as "no" or "yes".
- **Idempotent, re-runnable discovery.** Fetching the same source twice must not create duplicate
  jobs and must not crash; it must update what changed and leave what didn't.
- **Fail loud, fail isolated.** One job source failing (timeout, schema change, 5xx) must not
  abort the discovery run for other sources. Errors are captured per-source with status and
  message, surfaced in the UI, and logged with structured fields.
- **Safety features are architectural, not bolted on.** Even though autonomous submission is not
  implemented in Phase 1, the schema and module boundaries already reserve the places where the
  authorization policy engine, daily limits, emergency pause switch, and audit log will attach in
  later phases (see §8 and `docs/data-model.md`).

## 3. High-level system diagram

```
┌─────────────────────────┐        HTTPS (JSON)        ┌───────────────────────────────┐
│  Frontend (React + TS)  │ ──────────────────────────▶ │  Backend (FastAPI)             │
│  Vite dev server (5173) │ ◀────────────────────────── │  Uvicorn (8000)                │
└─────────────────────────┘                             │                                │
                                                          │  ┌──────────────────────────┐  │
                                                          │  │ API layer (routers)      │  │
                                                          │  └────────────┬─────────────┘  │
                                                          │               │                │
                                                          │  ┌────────────▼─────────────┐  │
                                                          │  │ Service layer            │  │
                                                          │  │ (business logic, typed)  │  │
                                                          │  └──┬──────┬──────┬────────┬─┘  │
                                                          │     │      │      │        │    │
                                              ┌───────────┘     │      │      │        └──────────┐
                                              │                 │      │      │                   │
                                     ┌────────▼───────┐ ┌───────▼───┐ ┌▼──────────┐   ┌────────────▼────┐
                                     │ Job source      │ │ Eligibility│ │ Scheduler │   │ Repository /    │
                                     │ adapters        │ │ & scoring  │ │(APScheduler)│  │ SQLAlchemy ORM  │
                                     │ (Greenhouse,    │ │ engine     │ │ discovery  │   │                 │
                                     │ Lever, Ashby)   │ │ (rule-based)│ │ jobs       │   └────────┬────────┘
                                     └────────┬────────┘ └────────────┘ └────────────┘            │
                                              │ HTTPS (httpx, retries/timeouts)                    │
                                              ▼                                                     ▼
                                     ┌──────────────────┐                                 ┌───────────────────┐
                                     │ Public job board  │                                 │ PostgreSQL         │
                                     │ APIs (untrusted)  │                                 │ (Alembic-migrated) │
                                     └──────────────────┘                                 └───────────────────┘
```

## 4. Repository layout

```
careerpilot/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app factory, startup wiring
│   │   ├── core/                   # config, logging, db session, exceptions
│   │   ├── models/                 # SQLAlchemy ORM models (one module per bounded context)
│   │   ├── schemas/                # Pydantic request/response schemas
│   │   ├── api/                    # FastAPI routers (thin HTTP layer only)
│   │   ├── services/               # business logic, orchestration, pure-ish functions
│   │   ├── sources/                # job source adapters (greenhouse/lever/ashby) + registry
│   │   ├── scheduling/             # APScheduler setup and discovery job wiring
│   │   └── tests -> (see backend/tests)
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── fixtures/                # recorded/sample API payloads for offline tests
│   ├── alembic/
│   │   ├── versions/
│   │   └── env.py
│   ├── alembic.ini
│   ├── pyproject.toml / requirements*.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── api/                     # typed fetch client for backend endpoints
│   │   ├── components/
│   │   ├── pages/
│   │   ├── types/
│   │   └── main.tsx / App.tsx
│   ├── index.html, vite.config.ts, tailwind.config.js, tsconfig.json
│   └── package.json
├── docs/
│   ├── architecture.md
│   ├── data-model.md
│   └── implementation-plan.md
├── docker-compose.yml
├── .gitignore
└── README.md
```

## 5. Module map (all 15 modules → Phase 1 status)

| # | Module | Phase 1 status |
|---|--------|------------------|
| 1 | Candidate Profile & Verified Fact Vault | **Partial.** Core profile fields (grad date, work authorization, sponsorship) implemented directly on the candidate profile. The generalized fact vault (arbitrary Q&A facts with provenance/confidence, used by the Answer Library) is designed in the data model but not implemented. |
| 2 | Configurable Job Source Registry | **Implemented.** `job_sources` table + admin-editable config for which employer boards to poll per provider. |
| 3 | Job Discovery & Normalization | **Implemented** for Greenhouse, Lever, Ashby. |
| 4 | Job Deduplication | **Implemented.** Canonical URL normalization + content hash + per-source external ID uniqueness. |
| 5 | Eligibility Checking | **Implemented**, rule-based only (work authorization / sponsorship / grad-date window / location). |
| 6 | Explainable Match Scoring | **Implemented**, rule-based with a reasons breakdown returned to the UI. |
| 7 | Resume Tailoring & Versioning | Not built. Schema reserves `resumes`/`resume_versions` tables conceptually (documented, not migrated). |
| 8 | AI Provider Management | Not built. Interface sketched in architecture only; no code. |
| 9 | Application Answer Library | Not built. |
| 10 | Form Automation Adapters | Not built. |
| 11 | Submission Authorization Policy Engine | Not built. Autonomous submission stays disabled by construction — there is no submission code path in Phase 1. |
| 12 | Application Queue & State Machine | Not built. |
| 13 | Application Tracker | Not built. |
| 14 | Analytics & Notifications | Not built beyond discovery-run status surfaced in the dashboard. |
| 15 | Privacy, Security & Audit Logging | **Partial.** Structured logging, secrets via env vars/`.env` (gitignored), no PII in logs. Full audit-log table deferred. |

## 6. Backend module boundaries (Phase 1)

- `app/core` — settings (Pydantic `BaseSettings`), DB engine/session factory, structured logging
  config, shared exceptions. No business logic.
- `app/models` — SQLAlchemy declarative models only. No HTTP, no provider-specific logic.
- `app/schemas` — Pydantic schemas for API I/O. Converts between wire format and internal types.
  Enforces validation (e.g., enum values, string lengths) at the boundary.
- `app/sources` — one subpackage per provider (`greenhouse/`, `lever/`, `ashby/`) each exposing a
  `fetch_jobs(board_token) -> list[RawJobPosting]` typed function, plus a shared
  `base.JobSourceAdapter` protocol. All HTTP specifics (pagination, response shape) are isolated
  here. A `registry.py` maps `job_sources` DB rows to the correct adapter.
  See the `httpx` client wrapper details for rate limiting and retry/backoff policy.
- `app/services` — `discovery_service` (orchestrates adapters → normalization → dedup →
  persistence, records a `discovery_run`), `job_service` (save/dismiss state), `eligibility_service`
  (rule evaluation), `candidate_service` (profile/preferences CRUD). Services depend on
  repositories/ORM sessions passed in, not on FastAPI request objects, so they're unit-testable.
- `app/api` — FastAPI routers; validate input via Pydantic, call exactly one service method, map
  service exceptions to HTTP errors. No SQL/ORM calls directly in routers.
- `app/scheduling` — APScheduler `BackgroundScheduler` configured from settings
  (`DISCOVERY_INTERVAL_MINUTES`), calls the same `discovery_service` entry point the manual
  "Run discovery" button uses, so there is exactly one code path for discovery.

## 7. Error handling, timeouts, retries, rate limits

- All outbound HTTP calls use a shared `httpx.Client`/`AsyncClient` wrapper
  (`app/sources/http.py`) configured with:
  - connect/read timeouts (default 10s, configurable),
  - bounded retries with exponential backoff + jitter on connection errors and 429/5xx responses,
  - a minimum delay between requests to the same host (simple token-bucket / sleep-based limiter),
  - a capped number of pagination pages per run to prevent runaway loops.
- Adapter-level failures (timeout, non-2xx after retries, malformed JSON) are caught and converted
  into a `JobSourceFetchError` with a human-readable message; the discovery service records this
  on the `discovery_run_sources` row and continues with the next source rather than aborting the
  run.
- API-layer errors are translated to appropriate HTTP status codes (404 for missing resources,
  422 for validation, 503 for "discovery already running" conflicts, 500 with a generic message
  for unexpected errors — never leaking stack traces or internal details to the client response
  body; full detail goes to structured logs only).

## 8. Where later-phase safety requirements will attach (not built in Phase 1)

These are listed so that Phase 1 code does not have to be reworked later:

- **Submission Authorization Policy Engine**: will sit between the Application Queue and Form
  Automation Adapters; checks per-platform enablement flags, standing authorization rules, and
  daily submission limits before any submission attempt is made. Phase 1 has none of this code,
  so no submission can occur even accidentally.
- **Emergency pause switch**: planned as a single settings-backed boolean (`SUBMISSIONS_PAUSED`)
  checked at the top of the (not-yet-built) submission worker loop, plus an admin endpoint to flip
  it. Documented now, implemented when the submission system exists.
- **Human review gate for unknown/sensitive answers**: the Answer Library (module 9) and
  Application Queue (module 12) will include an explicit `blocked_pending_review` state whenever a
  required screening answer is unknown or sensitive. Not built in Phase 1.
- **Audit logging**: the data model reserves space for an `audit_logs`-style table (see
  `docs/data-model.md` §"Future (not migrated in Phase 1)"); no autonomous action will be allowed
  to ship later without writing to it first.

## 9. Frontend architecture (Phase 1)

- Vite + React + TypeScript + Tailwind CSS. No server-side rendering; pure SPA talking to the
  FastAPI backend over `fetch`.
- `src/api/client.ts` — a small typed wrapper around `fetch` (base URL from
  `import.meta.env.VITE_API_BASE_URL`), with typed request/response interfaces matching the
  backend Pydantic schemas.
- `src/pages/Dashboard.tsx` — the only Phase 1 page: candidate profile summary, preferences,
  job list (saved/dismissed/new), "Run discovery" button, and the latest discovery run status.
  All data comes from real backend endpoints; **no hardcoded job data**. Loading/empty/error UI
  states are implemented explicitly per data-fetching hook, not simulated.
- State management: React Query–style data fetching is implemented with small custom hooks using
  `useState`/`useEffect` to avoid adding a dependency in Phase 1; revisit if complexity grows.

## 10. Testing strategy

- **Unit tests** (`backend/tests/unit`): normalization, dedup key computation, eligibility rules,
  match scoring, Pydantic schema validation — no network, no DB (or SQLite in-memory where a DB
  is unavoidable for a unit-level test).
- **Integration tests** (`backend/tests/integration`): real PostgreSQL (the `careerpilot_test`
  database), real Alembic migrations applied, FastAPI `TestClient`, and **mocked/fixture HTTP
  responses** for job source adapters (via `httpx` transport mocking or `respx`) — recorded,
  realistic Greenhouse/Lever/Ashby payloads live in `backend/tests/fixtures/`. No real network
  calls happen in CI/test runs by default.
- A small number of **manual/opt-in live checks** may hit real public job board endpoints during
  development to validate adapters against reality, but these are not part of the default test
  suite (so CI stays deterministic) and are explicitly noted when run.
