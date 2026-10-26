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

Per the user's explicit instruction at the time, Phase 2 (resume tailoring, AI provider
management, answer library, form automation, submission authorization engine, application
queue/state machine, tracker, analytics, full audit logging — and eventually, only within
configured standing authorization and after end-to-end testing, autonomous submission) had **not**
been started as of this writing. It has since begun under further direction: §5 (job
discovery/filtering/matching quality fixes) and §6 (milestone 2.1, resume upload/parsing/verified
facts) are now done. Form automation, submission authorization, and autonomous submission remain
entirely unimplemented and out of scope until a dedicated phase is explicitly scoped for them.

## 5. Phase 2 increment: job discovery, filtering & matching improvements

Done ahead of full Phase 2 because it fixes real quality issues in the existing Phase 1 discovery
pipeline, rather than adding new modules (7–13) to the system.

- [x] **1. Deterministic sorting.** `GET /api/jobs?sort=` supports `score_desc` (default),
      `score_asc`, `most_eligible_first`, `newest_first`, `oldest_first`, `company_asc`,
      `company_desc` — all computed in SQL across the *entire* filtered result set (not just the
      currently-loaded page) and always tie-broken by `Job.id` for determinism.
      (`app/services/job_service.py::list_jobs`.)
- [x] **2. Combinable advanced filters, display-only.** Minimum match score, job category,
      employment type, remote/hybrid/on-site, eligibility, company (substring), location
      (substring), posting age (`posted_within_days`, only applied when `posted_at` is actually
      known), and saved/dismissed/not-yet-reviewed state — all combinable, all applied in SQL
      before pagination (fixing a real pre-existing bug where filtering happened *after*
      pagination). A `view=recommended` / `view=all` toggle selects a pre-baked filter preset;
      `all` applies none of it, matching the pre-existing "no params → everything" contract.
      Filtering never deletes or mutates a `Job` row — see the integration test
      `test_filtering_never_deletes_jobs_from_the_database`. Frontend: "Clear filters" button in
      `JobsSection.tsx` resets all filter state back to empty.
- [x] **3. Eligibility/relevance/matching fix** (see `docs/architecture.md` §6a for the full
      writeup). Added `Relevance` (separate from `Eligibility`) and `SeniorityLevel` /
      `is_non_technical` title-keyword inference (`app/sources/normalize.py`). A
      `Relevance.NOT_RELEVANT` verdict caps the match score via `apply_relevance_cap`.
      `min_match_score_to_surface` is now actually enforced by `view=recommended` (previously
      never enforced anywhere — this was the root cause of the reported bug: an "Administrative
      Business Partner" role in Singapore shown as `eligible` at a 5/100 score despite a
      configured floor of 51). A one-time backfill (`scripts/backfill_job_classification.py`) was
      run against `careerpilot_dev` to reclassify the ~2127 already-discovered jobs and recompute
      every candidate's assessments, since discovery itself only reclassifies a job when its
      content changes.
- [x] **4. Job card redesign.** Each card now shows company, position, location, employment type,
      match score, eligibility *and* relevance as visually distinct badges, an always-visible
      "why this ranking" line (never silently blank), verified-vs-unverified posting date,
      save/dismiss buttons, a working "View original posting" link, and a disabled
      "Apply with AI — Coming soon" button (`frontend/src/components/JobCard.tsx`).
- [x] **5. Documentation for the future AI Application Agent.** `docs/architecture.md` §11 now
      specifies the ten requirements (opening supported forms, resume tailoring/upload, field
      auto-fill, drafting free-response answers from verified facts, a learning answer library,
      asking rather than guessing on missing info, gated autonomous-submission mode, hard safety
      boundaries, genuine-confirmation-only status updates, duplicate-submission prevention +
      emergency stop) in detail. **No code for any of this was written this iteration**, per
      explicit instruction — documentation only.

Tests: 112 pre-existing backend tests still pass unmodified; 14 new backend integration tests
cover sorting/filtering/pagination/views (`tests/integration/test_jobs_api.py`); unit tests for
`infer_seniority_level`/`infer_is_non_technical` and the relevance/scoring-cap logic bring the
full backend suite to **119 passed**. Frontend: `tsc -b`, `npm run build`, and `npm run lint`
(`oxlint`) all pass with no errors.

A real, pre-existing migration-plumbing bug was also found and fixed in the course of this work:
`alembic/env.py` unconditionally overwrote whatever `sqlalchemy.url` a caller had already set on
the `Config` object, which silently defeated `tests/conftest.py`'s attempt to run migrations
against `careerpilot_test` specifically — the test suite had only been passing because the dev
and test schemas were kept in sync by hand. `env.py` now respects an already-set URL and only
falls back to `settings.database_url` when none was provided.

## 6. Phase 2 milestone 2.1 — resume upload, parsing, and verified fact storage

Scope, per the user's explicit "start with milestone 2.1 only": upload a PDF/DOCX resume,
extract education/skills/projects/experience/achievements, and store them as verified-pending
`candidate_facts`. **Not** in scope for 2.1 (deferred to 2.2–2.4): AI provider integration, job
description analysis, tailored resume generation/diffing, and PDF/DOCX export. No application
form automation or submission code was added — none exists anywhere in the codebase.

### 6.1 Dependencies added (backend only; all directly used by this milestone)

- `python-multipart==0.0.32` — required by FastAPI/Starlette to parse `multipart/form-data`
  uploads (`UploadFile`/`File(...)`).
- `pypdf==6.21.2` — PDF text extraction.
- `python-docx==1.2.0` — DOCX text extraction (also used, with no extra dependency, to build
  in-memory DOCX fixtures for tests).

No frontend dependency was added; no frontend code was written yet for this milestone (see §6.5).

### 6.2 Database changes

One migration, `alembic/versions/6503438e5cd3_add_resumes_and_candidate_facts.py` (autogenerated,
reviewed, applied as-is — `downgrade()` drops both tables in dependency order): two new tables
(`resumes`, `candidate_facts`) and five new native Postgres enum types
(`resume_file_format_enum`, `resume_parse_status_enum`, `fact_type_enum`, `fact_source_enum`,
`fact_verification_status_enum`). Full column-level documentation: `docs/data-model.md` §2a.
Applied to `careerpilot_dev` via `alembic upgrade head`; `careerpilot_test` is migrated to head
automatically by the existing `tests/conftest.py` fixture on every test run (no manual step
needed there, consistent with how every prior migration has been handled).

### 6.3 Files added/changed

New: `app/models/resume.py`, `app/resume_parsing/__init__.py`, `app/resume_parsing/extractors.py`,
`app/resume_parsing/section_parser.py`, `app/schemas/resume.py`, `app/services/resume_service.py`,
`app/api/resumes.py`, the migration above, and three test files (`tests/unit/test_resume_extractors.py`,
`tests/unit/test_resume_section_parser.py`, `tests/integration/test_resumes_api.py`).
Changed: `app/models/enums.py` (+5 enums), `app/models/__init__.py` (exports), `app/core/config.py`
(+`resume_storage_dir`, `+resume_max_upload_mb` settings), `app/core/exceptions.py` (+3 exception
classes), `app/main.py` (registered the two new routers), `requirements.txt` (+3 packages).
No existing file's existing behavior was modified — every change to a shared file was additive.

### 6.4 Key architectural decisions

- **No numeric confidence score.** `candidate_facts.verification_status` (`unverified → verified
  | edited | rejected`) replaces the numeric `confidence` column sketched in the original
  `docs/data-model.md` §5 draft. Reasoning: a number implies false precision from a deterministic
  keyword/regex parser and risks being treated as "good enough to trust" past some threshold —
  directly in tension with "never fabricate" and "use AI for language, not for inventing facts."
  An explicit human action is required to move a fact out of `unverified`, and reverting back to
  `unverified` is rejected by the API (`CandidateFactUpdate` validator) since that status only
  describes the initial, not-yet-reviewed extraction state.
- **Deterministic parsing only, zero AI calls.** `app/resume_parsing` does keyword/regex-based
  section and date-range detection — no AI model is invoked, matching the milestone's framing
  ("prefer deterministic transformations where appropriate"; AI involvement starts in 2.2/2.3 for
  language improvement and relevance selection, never fact invention). Its module docstring
  states there are no network calls in the subpackage, so "don't send resume content to a cloud
  AI provider without authorization" is true by construction here, not configuration.
  **Always-at-least-one-fact guarantee.** Non-empty resume text that doesn't match any known
  section header still produces exactly one `FactType.OTHER` fact containing the full raw text —
  content is never silently dropped, and section structure is never invented where the source
  text doesn't have it.
- **Resume immutability is structural.** No PATCH/PUT/DELETE route exists for `/api/resumes/{id}`;
  verified via an integration test asserting both return `405`. The only persisted mutation path
  anywhere in this milestone is `PATCH /api/candidate/facts/{id}`.
- **Testable without a running AI/network dependency or global-state monkeypatching.**
  `resume_service.upload_resume()` takes `storage_dir`/`max_upload_mb` as explicit parameters
  (mirroring the pre-existing `app/sources/http.py` pattern) instead of calling `get_settings()`
  internally, so tests pass a `tmp_path`-backed directory and never write to the real
  `backend/storage/resumes/` (confirmed empty after the full suite run). PDF/DOCX test fixtures
  are generated in-memory (a hand-assembled, byte-offset-correct minimal PDF; a real DOCX built
  with the same `python-docx` library the extractor itself uses) rather than checking in binary
  fixture files or adding a PDF-generation dependency.

### 6.5 Test results

```
backend> pytest
148 passed, 1 warning in 20.24s
```

29 new tests (6 unit extractor tests, 10 unit section-parser tests — synthetic "Jane Doe" fixture
text, never the candidate's real resume — and 13 integration tests covering upload success for
both formats, missing-candidate 404, unsupported-extension 415, oversized-file 413, graceful
malformed-file failure with the original upload still persisted, listing, fact filtering, the
verify/edit/reject review flow, the `unverified`-reversion rejection, and resume-immutability
405s). All 119 pre-existing Phase 1/2 backend tests still pass unmodified — nothing in this
milestone touched existing behavior. No frontend test command was run because no frontend code
was written for this milestone yet (see §6.6).

### 6.6 Frontend (added after initial backend-only report, same milestone)

`frontend/src/components/ResumePanel.tsx`, wired into `Dashboard.tsx` between the preferences
editor and the job source registry: a file-upload form (`.pdf`/`.docx`), an uploaded-resumes list
with parse-status badges, and an extracted-facts list filterable by type/status with
Verify/Edit/Reject actions per fact (`PATCH /api/candidate/facts/{id}` — editing re-uses the
same backend rule that auto-promotes a fact to `edited` when no explicit status is sent, and the
UI disables the "Verify" button once already verified rather than relying on the backend to
reject a no-op). `frontend/src/api/types.ts` and `client.ts` gained the matching types and five
new client methods (`uploadResume` uses a real `FormData`/`multipart` request, intentionally not
reusing the generic JSON `request()` helper). No new frontend dependency was added.

Verified: `tsc -b --noEmit` clean, `npm run build` clean (bundle output unchanged in shape from
before), `npm run lint` (`oxlint`) clean. Additionally smoke-tested against a **live** `uvicorn`
process (not just the `TestClient`) hitting the real `careerpilot_dev` database: uploaded a real
generated PDF via `curl.exe` multipart, confirmed `education`/`skill` facts were extracted with
the exact shapes the UI renders, confirmed the verify action and the unverified-reversion 422 and
the resume-immutability 405 all behave identically to the integration tests. The smoke-test
resume/fact rows were deleted afterward and `backend/storage/` was removed, leaving the real
candidate profile (the only pre-existing row) untouched.

### 6.7 Explicitly not done in this milestone (deferred)

- Milestones 2.2 (AI provider abstraction/config), 2.3 (job-specific tailoring/diffing), and 2.4
  (DOCX/PDF export, versioning, E2E tests) are entirely unstarted, as instructed.

Status: **milestone 2.1 (backend + frontend) is implemented, tested, and live-smoke-tested.**
Stopped here per the user's explicit instruction, pending their review and approval before
proceeding to milestone 2.2.
