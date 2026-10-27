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
- **Phase 2.1 / 2.2 (implemented)**: deterministic resume parsing, canonical knowledge base,
  answer library, optional Gemini drafts. See §6–§7.
- **Phase 2.3 (this effort)**: job-specific application preparation — JD analysis,
  qualification matching, resume tailoring/export, and job-specific answer drafts.
  **Not** form automation or submission.
- **Phase 2.4+ (not started)**: form automation, submission authorization,
  application queue/state machine, tracker, analytics/notifications, full audit logging.
  Autonomous submission remains impossible because no submission code path exists.

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

### 6.8 Parsing / verification fix (same milestone, after live resume upload)

Root cause (verified against a real Google Docs PDF in `careerpilot_dev`): pypdf's default
`"plain"` extractor emitted **one token per line** (538/538 nonempty lines were a single word,
with a blank line between almost every word). `_split_into_blocks` then treated each blank as a
new record, so "University of California, Santa Cruz" became separate facts
`University` / `of` / `California,` / `Santa` / `Cruz`. All 519 stored facts were unverified
single-token keys.

Fix:
- PDF extraction prefers `extraction_mode="layout"` and `text_normalize.normalize_extracted_text`
  rejoins leftover one-token streams without inventing words.
- Section parser emits one structured record per school / job / project / skill category.
- `POST /api/resumes/{id}/reprocess` re-reads the original stored file and replaces only
  UNVERIFIED facts (verified / edited / rejected facts and the file itself are kept).
- Review UI: field-level edit, expand raw text, per-record verify/reject, explicit
  "Verify selected" / "Reject selected", and a Reprocess button.

Backend suite after this fix: **166 passed**. Frontend `tsc -b`, `npm run build`, and `npm run lint` clean.

### 6.9 Second live-resume parser pass (same milestone)

A real Google Docs PDF still merged consecutive jobs/projects, truncated wrapped
bullets, glued skill tokens (`PythonJavaScriptTypeScriptSQLC++`), and split SHPE
from its description. Root cause: wrap tails after a bullet reset
`prev_was_bullet`, so the next heading was not treated as a new record; leftover
fragments were then used as employers; glued CamelCase splitting also broke
`FastAPI`.

Fix:
- `rejoin_wrapped_lines` attaches lowercase / date / short-period tails before
  the section parser runs, so headings stay headings.
- Work and project blocks split only on job headers or project titles
  (`Org - City, ST dates` vs `Name - subtitle`). Date-only lines and month-led
  ranges are never a new record. Missing employer/position/name is left null
  and flagged `needs_review` — never guessed.
- Glued skills are split only by consuming known skill names; leftover tokens
  stay whole (`FastAPI` is not Fast + API). Categories remain separate facts
  with `items` arrays. The review UI renders those as chips.
- Achievements group a heading plus the bullets under it (SHPE + description).
- Reprocess is unchanged: `POST /api/resumes/{id}/reprocess` replaces only
  UNVERIFIED facts. The original file and verified/edited/rejected facts stay.

Regression fixtures cover four consecutive projects (TaskFlow, GlucoRelay,
Spritz, PC Build Visual Builder), two consecutive jobs, wrapped bullets, glued
and table-style skills, and organization/activity grouping. No personal resume
file is committed.

Backend suite after this pass: **176 passed**. Frontend `tsc -b`, `npm run build`,
and `npm run lint` (`oxlint`) clean.

### 6.10 Resume deletion (same milestone)

`DELETE /api/resumes/{id}` removes one uploaded file and only that file's resume-specific
extracted records. Verified/edited facts are detached (`resume_id` set null) unless the caller
sets `delete_verified_facts=true`. Facts from other resumes, the candidate profile, preferences,
job listings, and saved jobs are not referenced. `is_primary` marks the current primary file;
deleting it while others exist requires `replacement_resume_id`. Dashboard confirmation dialog
states those rules before the request is sent.

### 6.11 Third live-resume parser pass: records, section scope, duplicates (same milestone)

A legitimate single-column text PDF produced 4 work records instead of 2, 1 project instead of 4,
and 24 skill records instead of 6 categories. Four independent causes, all reproduced on the stored
file before any change:

1. **A field label was read as a section heading.** `Technologies: Python, ...` under each project
   matched the Skills heading keyword `technologies`, so every project after the first was cut off and
   its title, stack and bullets flowed into Skills (the 24 records).
2. **A location+dates line was read as a job header.** `Santa Cruz, CA | September 2024 – Present`
   became its own work record, separated from `Employer — Position` and from the bullets (4 records).
3. **Two bullets glued on one layout line** (`• A. • B.`) were never split.
4. **DOCX list bullets carry no glyph** (Word stores them as list formatting), so a bullet was
   indistinguishable from a company line.

Fix (parsing layer only; architecture unchanged):

- `text_normalize.match_section_header`: a heading must stand alone on its line. The ambiguous label
  `technologies` is a heading only when ALL CAPS and alone. Trailing ` :` is accepted (`SKILLS :`).
- `entry_parser.py` (new): an explicit segmentation state machine for work and project sections. A
  location/date-only line is metadata of the current entry, never a record. After bullets, a non-bullet
  line starts a new entry; a completed header or blank line also starts one; sentence-fragment tails
  rejoin the previous bullet. Title-hint words assign employer vs position; if it cannot be decided,
  both stay `null`, the header text is kept in `unclassified_text`, and the record is flagged. A second
  position under one employer carries the employer over, flagged for review.
- `skill_items.py` (new): skills come only from a skills section; items must look like short noun
  phrases (sentences become a flagged `OTHER` fact); slash names (`Linux/Unix`, `Git/GitHub`) stay whole.
- `extractors.py`: Word list items (`numPr` or a `List ...` style) get a bullet glyph.
- Education keeps `location`; work keeps `location`; projects split `name` / `tagline` / `technologies`.

Verification and duplicates (`resume_parsing/dedupe.py`, `resume_service.py`):

- Every record carries `needs_review`, `review_reasons`, `ambiguous_fields`. Nothing is auto-verified.
- `POST /api/candidate/facts/bulk` refuses to **verify** any flagged fact (422) and is all-or-nothing.
  Flagged facts are verified or edited one at a time (the "Verify entire record" button).
- Uploading a byte-identical file returns the existing resume (`already_uploaded: true`); nothing is
  re-parsed or re-inserted.
- Extracted records identical in content to an already verified/edited record are skipped
  (`facts_skipped_duplicate`). A same-named record with different content is kept, flagged, and linked
  with `possible_duplicate_of`; the reviewed record is never modified. Reprocess does not resurrect a
  record the user rejected in that resume.
- Records stay isolated per `resume_id`: uploading or reprocessing one file never edits another file's
  records, and deleting a resume still only affects its own unverified records.

Tests: `tests/resume_fixtures.py` builds real multi-page PDFs and DOCX files (nothing binary is committed;
the content is fictional). `test_resume_regression_layouts.py` asserts 1 education / 2 work / 4 projects /
6 skill categories / 1 achievement on both formats and on a reordered layout, plus multiple positions at one
employer, six date formats, missing optional fields, wrapped descriptions, and an unclassifiable header.
Disabling the DOCX-bullet fix or restoring the old heading rule makes those tests fail.

Existing stored resumes are **not** re-parsed automatically. Use "Reprocess this file" to apply the new
parser; only unverified records are replaced.

## 7. Phase 2 milestone 2.2 — canonical profile, answer library, grounded drafts

Scope: an authoritative candidate knowledge base independent of any one resume, a reusable
answer library, and a disabled-by-default AI provider for grounded draft generation. **Not** in
scope: form automation, CAPTCHA/MFA, autonomous submission, resume tailoring, or answering
sensitive questions without explicit authorization.

Working branch: `feature/candidate-knowledge-base` (from `main` at `1fd6cce`). Commits are per
increment; nothing is pushed or merged to `main` without approval.

Decisions locked for this milestone (stated before increment 1):

- Extracted `candidate_facts` stay as the resume-scoped, traceable record. A new `canonical_facts`
  table is the knowledge base. Resume deletion never cascades onto it.
- Import of verified/edited extracted facts is **explicit** (not auto-promoted on verify). Exact
  content matches are skipped; same-identity different content becomes a `conflict` row. The
  active value is never overwritten.
- Work authorization / sponsorship / graduation date stay on `candidates` (eligibility source of
  truth). Sensitive answers will only read those fields when the candidate authorizes it.
- One AI provider first (Gemini), behind a common interface, disabled unless configured. Tests
  use a mock. Keys live only in environment variables (never the frontend, never git).

Increments:

1. Canonical fact models + migration + schema tests.
2. Import / dedupe / conflict service.
3. Canonical profile API + resume-delete isolation through the service.
4. Answer library models + API.
5. AI provider abstraction (Gemini + mock).
6. Grounded generation + sensitive-question gates.
7. Knowledge Base + Answer Library frontend.
8. Remaining integration tests and docs wrap-up.

### 7.1 Increment 1 — canonical fact models

New tables `canonical_facts` and `canonical_fact_sources` (see `docs/data-model.md` §2b).
New enums `canonical_fact_status_enum` (`active|conflict|archived`) and
`canonical_fact_origin_enum` (`resume_import|manual_entry|profile`). Existing extracted-fact
tables and resume-delete behavior are unchanged.

Changed files: `app/models/enums.py`, `app/models/canonical.py` (new), `app/models/__init__.py`,
`alembic/versions/a1b2c3d4e5f6_add_canonical_facts.py` (new),
`tests/integration/test_canonical_facts_schema.py` (new), `docs/data-model.md`,
`docs/architecture.md`, `docs/implementation-plan.md`.

Tests: `pytest tests/integration/test_canonical_facts_schema.py` → **5 passed**. Full backend
suite: **254 passed**.

Status: **milestone 2.2 increment 1 complete.**

### 7.2 Increment 2 — import, dedupe, conflicts

`app/services/canonical_service.py` promotes verified/edited extracted facts into
`canonical_facts`. Exact content matches add a provenance link and skip a new row.
Same-identity different content becomes `status=conflict` (`needs_review`); the active
value is never overwritten. Manual create starts unverified. Archive/delete affect only
the canonical row. Conflict resolution is an explicit `keep=existing|incoming` action.

Tests: `tests/unit/test_canonical_import.py`, `tests/integration/test_canonical_service.py`.

Status: **milestone 2.2 increment 2 complete.**

### 7.3 Increment 3 — canonical profile API

`/api/candidate/canonical-facts` (list/create/import/get/patch/archive/resolve/delete).
Resume deletion leaves canonical rows in place and only clears provenance pointers
(`resume_id` / `candidate_fact_id` SET NULL), including when verified extracted facts
are explicitly removed with the resume.

Tests: `tests/integration/test_canonical_api.py`.

Status: **milestone 2.2 increment 3 complete.**

### 7.4 Increment 4 — answer library

`application_answers` + `application_answer_facts`. CRUD at `/api/candidate/answers`.
Equivalent questions (normalized fingerprint) with the same text are rejected. Variants of
the same question are allowed; only one may be preferred. Sensitive categories must go
`draft → reviewed → approved`. Answers may link only to active verified/edited canonical facts.

Status: **milestone 2.2 increment 4 complete.**

### 7.5 Increment 5 — AI provider abstraction

`app/ai/` with a common `AnswerProvider` interface. Gemini is the first real adapter
(httpx, no extra SDK). A mock provider is used in tests. `AI_ENABLED` defaults to false;
the rest of CareerPilot works without a key. `GET /api/ai/status` reports availability
and never includes the API key. Failures (timeout, 429, missing key) raise `AIProviderError`
with a redacted message.

Status: **milestone 2.2 increment 5 complete.**

### 7.6 Increment 6 — grounded drafts and sensitive-question gates

`POST /api/candidate/answers/generate` retrieves verified canonical facts and approved
answers, calls the configured provider, and stores a `draft` / `ai_draft` answer with
the fact ids used. Sensitive categories are refused before any model call. Unverified
facts are never sent. Missing information is recorded on the draft. Provider failures
do not create a row.

Status: **milestone 2.2 increment 6 complete.**

### 7.7 Increment 7 — knowledge base and answer library UI

Dashboard panels for the canonical knowledge base (import, manual add, verify, archive,
conflict resolution, provenance) and the answer library (create, search, approve with a
required review step for sensitive questions, preferred flag, AI draft when configured).
AI remains off unless `AI_ENABLED` and a key are set.

Status: **milestone 2.2 increment 7 complete.**

### 7.8 Increment 8 — docs wrap-up

Architecture module map, README, and this plan now describe 2.2 as implemented for the
knowledge base, answer library, and optional Gemini drafts. Form automation and submission
remain explicitly out of scope.

Status: **milestone 2.2 complete on `feature/candidate-knowledge-base`.** Not merged to `main`.

## 8. Phase 2 milestone 2.2.1 — personalized writing style

Scope: a persistent writing-style profile, approved writing samples stored
separately from qualifications, style-aware grounded generation, and a rewrite
path that never overwrites an approved answer. **Not** in scope: form
automation, submission, or treating samples as verified facts.

Working branch: `feature/personalized-writing-style`. Branched from
`feature/candidate-knowledge-base` (`49f9260`), not local `main` (`1fd6cce`),
because 2.2 (canonical facts, answer library, Gemini) is not on `main` yet.

Decisions:

- One `writing_style_profiles` row per candidate, lazy-created with the
  candidate's stated defaults (professional-conversational, short-to-medium,
  specific technical detail, straightforward vocabulary, buzzword avoid-list).
- Writing samples are a separate table. They are never auto-classified as
  authentic user writing. Adopting a revised answer as a sample is explicit.
- Samples are untrusted prompt data: delimited, never allowed to override
  factual-grounding or safety rules.
- Rewrites create a new draft linked to the original. Approved answers are
  not overwritten.

Increments:

1. Writing style profile models + API.
2. Writing samples models + API.
3. Style-aware generation (profile + approved samples only).
4. Rewrite existing drafts with unsupported-claim flags.
5. Dashboard Writing Style section and compare/rewrite UI.
6. Docs wrap-up and full suites.

### 8.1 Increment 1 — writing style profile

`writing_style_profiles` plus `GET`/`PUT /api/candidate/writing-style`.
Missing profiles are created with editable defaults.

Status: **milestone 2.2.1 increment 1 complete.**

### 8.2 Increment 2 — writing samples

Separate `writing_samples` table with explicit user-written vs adopted
origins, fingerprint dedupe, length limits, and approve-for-style-reference.

Status: **milestone 2.2.1 increment 2 complete.**

### 8.3 Increment 3 — style-aware generation

Generation loads the writing profile and approved samples only. Samples are
delimiter-wrapped as untrusted data and cannot override factual grounding.

Status: **milestone 2.2.1 increment 3 complete.**

### 8.4 Increment 4 — rewrite drafts

`POST /api/candidate/answers/{id}/rewrite` creates a new draft linked to the
original. Approved answers are never overwritten. New proper nouns and years
are flagged as unsupported claims.

Status: **milestone 2.2.1 increment 4 complete.**

### 8.5 Increment 5 — writing style dashboard

Dashboard Writing Style section for preferences and samples. Answer library
can generate a personalized draft, rewrite using the profile, compare
original vs rewrite, edit the rewrite, and adopt an answer as a writing
sample.

Status: **milestone 2.2.1 increment 5 complete.**

### 8.6 Increment 6 — docs wrap-up

Architecture and this plan record 2.2.1. A synthetic comparison
(`python -m scripts.evaluate_writing_style`) showed a generic draft of 1277
characters that used an avoided phrase versus a personalized draft of 444
characters that stayed on the verified FastAPI/Redis facts. This does not
claim the system can detect or eliminate AI-sounding writing.

Status: **milestone 2.2.1 complete on `feature/personalized-writing-style`.**
Not merged to `main`.

## 9. Phase 2 milestone 2.3 — application preparation

Reconciles the existing plan's "2.3 tailoring/diffing" with this milestone:
preparation includes JD analysis, qualification matching, tailored resume
export, and job-specific answers. Form automation stays 2.4+.

Working branch: `feature/application-preparation` from
`feature/personalized-writing-style` (`e4f900a`).

Decisions:

- One open preparation per `(candidate, job)`. Repeat Prepare returns it.
  Cancelled rows stay for history; a new prepare may follow a cancel.
  Failed rows are kept and returned, not replaced.
- Job title, employer, description, apply URL, and content hash are snapshotted
  so later listing edits do not change this preparation.
- JD analysis is deterministic first (section/keyword). Items are `stated` or
  `inferred`. Matching uses only verified/edited canonical facts and explicit
  profile fields. No match without evidence.
- Tailoring reorders and optionally rewords existing facts. Original resume
  bytes are never modified. Visual design is not reproduced; an ATS-friendly
  CareerPilot layout is used and that limitation is recorded.
- Preparation answers are separate from the answer library. Approved library
  answers are copied/adapted, never overwritten. Sensitive questions are not
  auto-drafted.
- States are preparation-only: `preparing`, `needs_review`, `ready`, `failed`,
  `cancelled`. There is no submit action.

Increments:

1. Preparation models, snapshot, idempotent API.
2. Job-description analysis and qualification matching.
3. Deterministic resume tailoring.
4. PDF/DOCX export and original-resume preservation.
5. Job-specific answers (reuse + grounded drafts).
6. Dashboard Prepare Application UI.
7. Docs wrap-up and full suites.

### 9.1 Increment 1 — preparation records

`application_preparations` plus create/list/get/cancel. Repeat create for the
same job returns the open row. The job description is snapshotted.

Status: **milestone 2.3 increment 1 complete.**

### 9.2 Increment 2 — job analysis and matching

Deterministic extraction of stated vs inferred requirements, then matching
against verified facts and explicit profile fields only.

Status: **milestone 2.3 increment 2 complete.**
