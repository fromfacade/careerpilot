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
| 5 | Eligibility Checking | **Implemented**, rule-based only (work authorization / sponsorship / grad-date window / location). As of Phase 2, deliberately scoped to *hard application requirements only* — see §6a for why this is a separate concept from Relevance. |
| 6 | Explainable Match Scoring | **Implemented**, rule-based with a reasons breakdown returned to the UI; a `Relevance.NOT_RELEVANT` verdict caps the score (see §6a) so an out-of-scope role can never show a coincidentally high number. |
| 7 | Resume Tailoring & Versioning | **Implemented for Phase 2.3.1.** Uploaded files are resume profiles (category, approval, default). Prepare Application selects an approved original file and explains why. Tailoring is optional and never replaces the selected original. Generated PDFs are validated for extractable text. |
| 8 | AI Provider Management | **Partial (Phase 2.2).** Common `AnswerProvider` interface, Gemini adapter (httpx), mock for tests. Disabled unless `AI_ENABLED` and a key are set. Status endpoint never returns the key. Resume parsing still has zero AI calls. |
| 9 | Application Answer Library | **Implemented (Phase 2.2 / 2.2.1).** Manual and AI-draft answers, writing-style profile, approved writing samples as untrusted style references, grounded generation, and rewrite-without-overwrite. No form filling or submission. |
| 10 | Form Automation Adapters | **Detection only (Phase 2.4.1).** `POST /api/autofill/detect` classifies an allow-listed Greenhouse URL and maps fields in caller-supplied HTML. It does not open a browser, fill fields, attach files, or submit. Lever and Ashby URLs are recognized and rejected. |
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
answers for review. Phase 2.4.1 adds Greenhouse URL classification and
form-field detection only. Opening a browser, filling fields, uploading
a resume, and any submission remain unimplemented. This section is the
spec for that later work.

The fill increments will use a locally controlled headed Playwright
browser, with one adapter per site. The reason for that choice, and why
a browser extension is not the default, is recorded in
`docs/implementation-plan.md` §12. Detection stays a pure function of a
URL plus HTML so preparation still works when no browser is installed.

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
