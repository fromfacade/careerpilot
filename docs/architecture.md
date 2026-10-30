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
│   │   ├── resume_parsing/         # PDF/DOCX text extraction, whitespace repair, deterministic section parsing (Phase 2.1); no network calls
│   │   ├── ai/                     # Answer-provider interface, Gemini adapter, mock (Phase 2.2); disabled by default
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
| 1 | Candidate Profile & Verified Fact Vault | **Implemented for Phase 2.2.** Core profile fields stay on `candidates`. Resume-derived extracted facts (2.1) plus an independent canonical knowledge base (`canonical_facts`) with explicit import, conflict rows, and provenance that survives resume deletion. |
| 2 | Configurable Job Source Registry | **Implemented.** `job_sources` table + admin-editable config for which employer boards to poll per provider. |
| 3 | Job Discovery & Normalization | **Implemented** for Greenhouse, Lever, Ashby. |
| 4 | Job Deduplication | **Implemented.** Canonical URL normalization + content hash + per-source external ID uniqueness. |
| 5 | Eligibility Checking | **Implemented**, rule-based only (work authorization / sponsorship / graduation / location). Graduation uses an explicit requirement in the posting. A silent internship or new-grad posting does not fall back to a generic date window. Scoped to hard requirements — see §6a. |
| 6 | Explainable Match Scoring | **Implemented**, rule-based with a reasons breakdown returned to the UI; a `Relevance.NOT_RELEVANT` verdict caps the score (see §6a) so an out-of-scope role can never show a coincidentally high number. |
| 7 | Resume Tailoring & Versioning | **Implemented for Phase 2.3.1.** Uploaded files are resume profiles (category, approval, default). Prepare Application selects an approved original file and explains why. Tailoring is optional and never replaces the selected original. Generated PDFs are validated for extractable text. |
| 8 | AI Provider Management | **Partial (Phase 2.2).** Common `AnswerProvider` interface, Gemini adapter (httpx), mock for tests. Disabled unless `AI_ENABLED` and a key are set. Status endpoint never returns the key. Resume parsing still has zero AI calls. |
| 9 | Application Answer Library | **Implemented (Phase 2.2 / 2.2.1).** Manual and AI-draft answers, writing-style profile, approved writing samples as untrusted style references, grounded generation, and rewrite-without-overwrite. No form filling or submission. |
| 10 | Form Automation Adapters | **Greenhouse workflow (Phase 2.5.5 and 3.4.2).** Apply with CareerPilot prepares the application and fills approved fields in a headed Chromium window. Review Mode submits only after a fresh readiness check and a confirmation for that application. An active Auto-Apply grant can use that same click after a fresh authorization check. Success requires a receipt on the page. |
| 11 | Submission Authorization Policy Engine | **Review Mode confirmation, plus an opt-in Auto-Apply grant (Phase 3.4.2).** Review Mode still needs a current readiness result and an explicit confirmation of that employer and job. Auto-Apply is off until the user acknowledges it and sets a Greenhouse-only scope, limits, approved resumes, and an expiration time. Saving the grant does not submit. A later Apply click reloads the grant, holds one limit slot, and only then uses the existing Greenhouse submit path. |
| 12 | Application Queue & State Machine | **Partial (Phase 2.5.5).** `tracked_applications` moves through an authorized submit. `application_events` records each status change. The job-card workflow reuses one open preparation and one tracked row. |
| 13 | Application Tracker | **Partial (Phase 2.5.5).** The job card and the preparation detail show status, confirmation, submission time, history, and a correction when the outcome is unknown. |
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

### 6a. Eligibility vs. Relevance vs. Match Score (added Phase 2)

Three signals are computed per (job, candidate) and must never be collapsed into one verdict or
conflated in the UI:

- **Eligibility** (`Eligibility`: `eligible` / `ineligible` / `unknown`) — whether an *explicit,
  hard application requirement* is satisfied: work authorization/sponsorship, graduation-date
  window. This is narrow by design. A job can be fully `eligible` and still be a terrible fit —
  eligibility says nothing about whether the role is technical, senior-appropriate, or in-scope.
- **Relevance** (`Relevance`: `relevant` / `not_relevant` / `unknown`) — whether the posting falls
  within the candidate's stated career scope at all: is it a technical role, and is the seniority
  level appropriate for an early-career candidate? Computed from title-keyword inference
  (`SeniorityLevel`, `is_non_technical` — see `app/sources/normalize.py`), deliberately simple and
  explainable rather than ML-based. Absence of a seniority/category keyword yields `unknown`, never
  a silently-assumed "fine" — this project never treats missing information as satisfied.
- **Match score** (0–100) — numeric strength of alignment against the candidate's preferences
  (role category, location, employment type, remote/hybrid/on-site). If `Relevance.NOT_RELEVANT`,
  the score is capped at a low ceiling (10) via `apply_relevance_cap` regardless of how well
  secondary factors happen to line up, because a "decent" score on an out-of-scope role is
  coincidental, not meaningful.

**Concrete motivating example** (a real bug this fixes): an "Administrative Business Partner"
role in Singapore was shown as `eligible` (correctly — no sponsorship/grad-date blocker exists for
that posting) with a match score of 5/100, while the candidate's minimum-score-to-surface
preference was 51. Two separate problems, both now fixed:

1. The minimum-score preference (`min_match_score_to_surface`) was never actually enforced
   anywhere in job listing — fixed by `job_service.list_jobs`'s `view=recommended` behavior.
2. `eligible` alone was misleading without a visible, separate `relevance` signal — the job *is*
   eligible (no hard requirement blocks it) and simultaneously *not relevant* (non-technical,
   executive-titled role, completely outside a SWE job search). The UI renders both as distinct
   badges so neither implies the other.

### 6b. Resume upload & verified fact extraction (Phase 2.1)

- `app/resume_parsing` — pure, offline text processing only. Its module docstring states
  explicitly that no network calls happen anywhere in this subpackage; this is a structural fact,
  not a configuration flag, satisfying the requirement "do not send resume content to a cloud AI
  provider without explicit configuration and authorization" by construction for this milestone.
  - `extractors.py` — `extract_text(file_bytes, file_format)` dispatches to `pypdf` (PDF) or
    `python-docx` (DOCX, walking paragraphs and joining table *rows* so each cell does not
    become its own fact). PDF extraction prefers pypdf `extraction_mode="layout"` over the
    default `"plain"` mode: Google Docs / Word PDFs store each word as a separately positioned
    run, and plain mode emits one token per line. `text_normalize.py` then collapses column
    padding and, when a page is still ≥60% one-token lines, rejoins those tokens into readable
    lines while keeping section headers and bullets on their own line. Encrypted PDFs, zero-text
    PDFs, corrupt files of either format, and any other failure raise `ResumeExtractionError` —
    never silently return empty/partial text as if it were a success.
  - `section_parser.py` — deterministic (non-AI) section detection (a heading must stand alone
    on its line; the field label `Technologies:` is never a heading), then
    **one record per school / job / project / skill category**, not one record per line.
    Records stay in their parent section until the next heading. `entry_parser.py` segments work and
    project sections with an explicit state machine (location/date-only lines are metadata, never a
    record; wrapped bullets rejoin; a second position at one employer is a separate, flagged
    record). `skill_items.py` accepts skills only from skills sections and keeps names such as
    `Linux/Unix` whole. Education groups institution, location, degree, major, GPA, and dates when
    those substrings are present; work groups employer, position, location, dates, and bullets;
    projects group name, subtitle, technologies, and bullets. Fields the source text does not
    contain stay `null` — they are never guessed; when employer vs position cannot be told apart,
    both stay `null`, the text is preserved, and the record is flagged `needs_review`. `dedupe.py`
    skips extracted records identical to already-reviewed ones and flags same-name conflicts.
    Skills split only on comma/semicolon/pipe, never on spaces. Ordinary prose
    and leftover words such as "of" / "and" are never emitted as their own facts. **Always
    returns at least one fact for non-empty input**: when no headers are recognized, or a
    detected section is otherwise empty, the full raw text becomes a single `FactType.OTHER`
    fact rather than being dropped. Dates stay a verbatim substring (`dates_text`).
- `app/services/resume_service.py` — orchestrates upload: validates file size/extension against
  explicit parameters (`storage_dir`, `max_upload_mb` — not read from global settings internally,
  mirroring the existing `app/sources/http.py` convention, so the service is testable with a
  `tmp_path` without monkeypatching process-wide config), computes a SHA-256 checksum, writes the
  file under that checksum (never the client-supplied filename, to remove any path-traversal
  surface), persists the `Resume` row, then calls `resume_parsing` inside a `try/except
  ResumeExtractionError` so a parse failure still leaves the upload and the original file intact
  with `parse_status=failed` and a recorded error — it never discards an uploaded file just
  because parsing it failed. The sole mutation path for extracted facts is `update_fact`, which
  requires an explicit human action (edit content or change `verification_status`) and rejects
  reverting a fact back to `unverified`.
- `app/api/resumes.py` — `POST /api/resumes` (multipart upload), `GET /api/resumes`,
  `GET /api/resumes/{id}`, `GET /api/resumes/{id}/facts`,
  `POST /api/resumes/{id}/reprocess` (re-reads the stored file; replaces only UNVERIFIED facts;
  verified / edited / rejected facts and the file itself are untouched),
  `GET /api/candidate/facts?fact_type=&verification_status=`,
  `PATCH /api/candidate/facts/{id}`,
  `POST /api/candidate/facts/bulk` (explicit verify/reject of selected IDs; cannot set
  `unverified`; refuses with 422 to verify any fact flagged `needs_review`, all-or-nothing).
  Canonical knowledge base (`app/api/canonical.py`): `GET/POST /api/candidate/canonical-facts`,
  `POST /api/candidate/canonical-facts/import`, `PATCH/DELETE /api/candidate/canonical-facts/{id}`,
  archive and conflict-resolve actions. Import never overwrites an active value. Deleting a
  resume cannot cascade onto canonical rows. **No PATCH/PUT exists for a `Resume` row's file fields** — this is
  the concrete mechanism behind "maintain an immutable copy of the original resume."
- Storage: `backend/storage/resumes/` (configurable via `resume_storage_dir`), excluded from git
  via the pre-existing `backend/storage/` line in `.gitignore` — uploaded resumes and the PII
  they contain are never committed.
- Resume/fact data is strictly additive: no code in this module writes to the `candidates` table.
  Verified profile fields (graduation date, work authorization, etc.) are untouched by uploads.

### 6c. Application preparation (Phase 2.3)

`POST /api/preparations` creates or returns the open preparation for a
discovered job. The listing title, employer, description, apply URL, and
content hash are snapshotted so later board edits cannot change the
inputs. Analysis is deterministic: items are `stated` or `inferred`.
Qualification matching uses only verified/edited canonical facts and
explicit profile fields. An approved resume profile is selected
deterministically and explained. Tailoring is an explicit follow-up
action; the selected original file is downloaded unchanged. Optional
tailored DOCX/PDF exports use an ATS one-page intern layout: two or
three job-relevant projects, categorized skills, and extractable-text
plus page-break checks. The original visual design is not reproduced
for tailored drafts, and that limitation is stored on the row. Job-specific answers live on the
preparation and can be regenerated without changing the selected resume.
States (`preparing`, `needs_review`, `ready`, `failed`, `cancelled`) are
preparation progress only. There is no submit endpoint and no
form-automation adapter.

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
- `src/components/JobsSection.tsx` (added Phase 2) — "Recommended" vs. "All Jobs" view toggle, a
  sort dropdown (7 deterministic orderings, always tie-broken server-side by `Job.id`), a
  combinable advanced-filter panel with a "Clear filters" button, and page-at-a-time pagination
  driven by the real total count from the `X-Total-Count` response header (never just the count
  of the currently-loaded page). All filtering is display-only — see §6a and `job_service.list_jobs`
  — a job discovered once stays in the database no matter how it's filtered out of view.
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

## 11. Future: AI Application Agent (form automation and submission)

Phase 2.3 implemented offline application preparation: JD analysis,
qualification matching, tailored resume export, and job-specific draft
answers for review. Phase 2.4.1 adds Greenhouse URL classification and form-field
detection. Phase 2.4.2 adds a reviewable contact-mapping plan. Phase
2.4.3 adds the selected resume and approved answers to that plan.
Phase 2.4.4 opens one isolated headed Chromium window, fills the fields
the user approved, and can attach the selected resume. A Greenhouse job
whose public link is the employer career site still opens the
allow-listed Greenhouse form identified by that job's board token and
job id. Phase 2.4.5 attaches that resume under its original filename,
without renaming the stored file, and fills phone, dialing country,
city, and education only when a verified value exactly matches the
control. It does not submit. Phase 2.5.1 adds a readiness check for
graduation, work authorization, required fields, the approved resume,
approved answers, unanswered sensitive questions, an active CAPTCHA or
MFA challenge, job identity, and an already-submitted page. Unknown
eligibility stays `needs_review`. Optional demographic questions do
not block that check. Required sensitive or legal questions stay
manual. Phase 2.5.2 stores one `tracked_applications` row per job and
shows its status on the preparation list. Readiness can move that row
to `needs_review` or `ready_to_submit`. Phase 2.5.3 submits only after
a separate confirmation for the open session. A button click is stored
as submitted only when the employer page shows a receipt. Phase 2.5.4
keeps an uncertain result unknown until the user records what the
employer page showed, and that correction is stored in the status history.
Phase 2.5.5 starts that same path from Apply with CareerPilot on the job
card: one preparation, approved-field fill, and the existing confirmation
before anything is sent. Tailoring stays optional. An unsupported board
never opens a browser. Phase 3.1.1 classifies common Greenhouse questions
without inventing dates, GPA, or experience. Phase 3.1.2 reuses an approved
answer only when the question meaning, employer, role, and technology still
fit. Equivalent wording can match. A different employer or technology does
not autofill. Uncertain matches and time-sensitive library answers stay for
review. Drafts are not promoted, and sensitive questions stay manual.
Phase 3.1.3 drafts an open-ended question only when matching finds nothing.
The draft is grounded in verified facts and the current writing-style profile,
and it is not filled until the user approves it. GPA, graduation, start date,
and sensitive questions are never sent to the model. Phase 3.1.4 keeps a
question attached to its dropdown, radio, checkbox, or searchable list when
the control is redrawn, and fills a verified follow-up that appears after
another answer. A choice is used only when it is listed. A control that
cannot be matched is left for review. Phase 3.1.5 fills common searchable
dropdowns from one exact verified fact or approved answer, and the review
screen counts completed fields separately from the questions that still
need attention. Review Mode submission still requires an explicit confirmation.
Phase 3.1.6 matches a verified school or degree to one equivalent employer
option. The stored fact is left unchanged, and more than one match stays
for review. Phase 3.1 is complete. The same confirmation, readiness, and
duplicate-submission checks still decide whether an application can be sent.

Phase 3.4.1 stores a separate Auto-Apply grant on
`auto_apply_authorizations`. It is not a job-search preference. The
grant is off by default, Greenhouse-only, and active only after an
explicit acknowledgement, a future expiration time, and a scope of
categories, employment types, locations, a minimum match score, daily
and session limits, and approved resume profiles. An empty scope
authorizes nothing. Disabling the grant or letting it expire blocks a
future automatic submission. The decision function reads that Phase 3.1 readiness result. Phase 3.4.2
uses a permitted result as the authorization for one click on the existing
Greenhouse submit path. The grant is reloaded immediately before that click,
and a locked reservation keeps two applications from sharing the last slot.
Review Mode still requires a confirmation for that job. A paused Auto-Apply
attempt leaves the browser open and does not send itself later. CAPTCHA,
MFA, unknown eligibility, an unapproved resume or answer, a required
sensitive question, and an already submitted or unconfirmed application
stay outside the grant.

The browser is a locally controlled headed Playwright window, with one
adapter per site. The reason for that choice, and why a browser
extension is not the default, is recorded in
`docs/implementation-plan.md` §12. Detection stays a pure function of a
URL plus HTML so preparation still works when no browser is installed.
State-changing browser routes require a local token in addition to the
localhost Host and Origin checks.

The agent's responsibilities, once built, will be:

1. **Open supported application forms.** Given a job's `apply_url`, detect and open the
   application form for platforms the Form Automation Adapters module explicitly supports
   (allow-listed, not a generic scraper).
2. **Tailor and upload a resume.** Select/generate a resume version (module 7) relevant to the
   specific posting and attach it to the form.
3. **Auto-fill standard fields.** Name, email, phone, school, graduation date, links, etc. from
   the verified Candidate Profile / Fact Vault (module 1) — never fabricated, never guessed.
4. **Draft personalized free-response answers.** Using verified candidate facts plus writing
   samples (module 9, Application Answer Library) to produce draft answers to open-ended
   application questions, always presented for review before use.
5. **Maintain a reusable, learning answer library.** Approved answers are stored and reused for
   similar future questions; the library is updated based on the candidate's edits to drafts, so
   quality improves over time instead of regenerating from scratch every time.
6. **Detect missing information and ask, rather than guess.** If a form field or question
   requires information not present (and not inferable with high confidence) in the Fact Vault,
   the agent must pause and explicitly ask the candidate — mirroring this project's existing
   "never silently assume" rule for eligibility/relevance (§6a).
7. **Support an explicit autonomous submission mode**, gated by:
   - a standing authorization policy the candidate configures in advance (what kinds of
     applications may be auto-submitted, and under what conditions),
   - a per-site/per-platform permission check (submission is only attempted on platforms
     explicitly enabled, never a default-allow),
   - and a requirement that every answer used was previously verified/approved — no
     never-reviewed answer is used.
8. **Hard safety boundaries, non-negotiable:**
   - Never fabricate personal information under any circumstance.
   - Never attempt to bypass anti-bot controls (CAPTCHAs, bot-detection challenges) — if a
     platform blocks automation, the agent stops and flags it for manual handling, it does not
     try to work around the block.
   - Never submit on a platform not explicitly present on the allow-list, no matter how
     confident the match score or answer quality.
9. **Record genuine submission confirmations only.** An application is only marked `submitted` in
   the Application Tracker (module 13) when the target platform returns real confirmation (a
   confirmation page/ID/email receipt) — never optimistically marked based on "the form was
   filled out" or "no error was thrown".
10. **Prevent duplicate submissions and support an emergency stop.** The Application Queue state
    machine (module 12) must make it structurally impossible to submit the same
    (candidate, job) pair twice, and a single, always-checked kill switch (the "emergency pause
    switch" already reserved in §8) must be able to halt all in-flight and future autonomous
    submissions immediately.

Form filling, CAPTCHA/MFA bypass, and application submission have no
code path in this repo. Detection reports captcha and MFA as blockers
and does not act on them. Preparation materials cannot be submitted
from the dashboard or the API.
