# CareerPilot — Data Model

PostgreSQL via SQLAlchemy models, migrated with Alembic. All tables use a surrogate
`BIGINT`/`UUID`-free integer primary key (`id`, `BIGSERIAL`) for simplicity and FK join
performance, plus `created_at`/`updated_at` timestamps (UTC, `TIMESTAMPTZ`) with DB-side defaults.

Enums are implemented as native PostgreSQL enum types via SQLAlchemy `Enum`. Every enum that
represents a safety- or eligibility-relevant fact includes an explicit `unknown` member — we never
use `NULL` to mean "don't know" for these fields, so "unknown" can be queried, displayed, and
reasoned about explicitly instead of being confused with "not applicable" or a forgotten column.

## 1. Entity-relationship overview (Phase 1 tables only)

```
candidates 1───1 candidate_preferences
candidates 1───* candidate_location_preferences
candidates 1───* candidate_role_preferences
candidates 1───* job_candidate_states ──* jobs
candidates 1───* job_assessments ──* jobs

employers 1───* job_sources
job_sources 1───* jobs
jobs 1───* job_locations

job_sources 1───* discovery_run_sources
discovery_runs 1───* discovery_run_sources
```

## 2. Phase 1 tables

### 2.1 `candidates`

The candidate profile. Single-tenant for now (one row expected in practice) but modeled as a
table so later phases (multiple resume targets, multi-user) don't require a redesign.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | |
| `full_name` | `TEXT` | NOT NULL | |
| `email` | `TEXT` | NOT NULL, UNIQUE | |
| `phone` | `TEXT` | NULL | |
| `school` | `TEXT` | NULL | e.g. "UC Santa Cruz" |
| `degree_level` | `degree_level_enum` | NOT NULL, default `unknown` | `associate, bachelors, masters, phd, bootcamp, other, unknown` |
| `major` | `TEXT` | NULL | |
| `graduation_date` | `DATE` | NULL | Nullable because precision may be month-only; paired with `graduation_date_precision` |
| `graduation_date_precision` | `date_precision_enum` | NOT NULL, default `unknown` | `exact, month, unknown` |
| `work_authorization_status` | `work_auth_status_enum` | NOT NULL, default `unknown` | `us_citizen, permanent_resident, visa_holder, requires_sponsorship, unknown` |
| `requires_sponsorship` | `tri_state_enum` | NOT NULL, default `unknown` | `yes, no, unknown` — kept distinct from `work_authorization_status` because some visa holders still don't need *future* sponsorship |
| `current_location` | `TEXT` | NULL | free text city/region, for display only — not used in matching |
| `linkedin_url` | `TEXT` | NULL | |
| `github_url` | `TEXT` | NULL | |
| `portfolio_url` | `TEXT` | NULL | |
| `base_resume_filename` | `TEXT` | NULL | unused legacy placeholder — Phase 2.1's resume module uses the separate `resumes` table (§2a.1) instead, so a candidate can have more than one uploaded resume over time; this column is not read or written by any code |
| `notes` | `TEXT` | NULL | free-form, candidate-authored |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | updated on write |

### 2.2 `candidate_preferences`

One row per candidate holding scalar preference settings. Multi-valued preferences (locations,
role categories) are normalized into their own tables below so they can be prioritized/ordered
and queried efficiently.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | |
| `candidate_id` | `BIGINT` | NOT NULL, UNIQUE, FK → `candidates.id` ON DELETE CASCADE | one-to-one |
| `remote_ok` | `BOOLEAN` | NOT NULL, default `true` | |
| `target_employment_types` | `employment_type_enum[]` | NOT NULL, default `{}` | array of `internship, new_grad, full_time, contract, unknown` |
| `target_start_window_start` | `DATE` | NULL | e.g. 2027-03-01 for Spring 2027 |
| `target_start_window_end` | `DATE` | NULL | e.g. 2027-09-01 to cover through Summer 2027 |
| `min_match_score_to_surface` | `SMALLINT` | NOT NULL, default `0`, CHECK 0–100 | dashboard filter threshold |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL | |

### 2.3 `candidate_location_preferences`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | |
| `candidate_id` | `BIGINT` | NOT NULL, FK → `candidates.id` ON DELETE CASCADE | |
| `label` | `TEXT` | NOT NULL | e.g. `"California"`, `"Seattle"`, `"Remote"` |
| `location_type` | `location_pref_type_enum` | NOT NULL | `state, metro, remote` |
| `priority` | `SMALLINT` | NOT NULL, default `0` | lower = higher priority; used in scoring |
| UNIQUE | | `(candidate_id, label)` | |

### 2.4 `candidate_role_preferences`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | |
| `candidate_id` | `BIGINT` | NOT NULL, FK → `candidates.id` ON DELETE CASCADE | |
| `role_category` | `role_category_enum` | NOT NULL | `swe_backend, swe_frontend, swe_fullstack, infrastructure, ai_engineering, cybersecurity, qa, it_support, other` |
| `priority` | `SMALLINT` | NOT NULL, default `0` | lower = higher priority |
| UNIQUE | | `(candidate_id, role_category)` | |

### 2.5 `employers`

A company whose job boards we poll. Kept separate from `job_sources` because one employer could
in theory expose boards on more than one provider, and so human-readable employer metadata isn't
duplicated per source.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | |
| `name` | `TEXT` | NOT NULL, UNIQUE | |
| `careers_url` | `TEXT` | NULL | informational only |
| `notes` | `TEXT` | NULL | |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL | |

### 2.6 `job_sources`

The **configurable job source registry**: each row is one employer's board on one provider,
pollable independently. This is the unit of configuration the registry UI/config file manages.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | |
| `employer_id` | `BIGINT` | NOT NULL, FK → `employers.id` ON DELETE CASCADE | |
| `provider` | `job_provider_enum` | NOT NULL | `greenhouse, lever, ashby` |
| `board_token` | `TEXT` | NOT NULL | provider-specific identifier (Greenhouse board token / Lever site / Ashby org slug) |
| `is_enabled` | `BOOLEAN` | NOT NULL, default `true` | registry on/off switch |
| `fetch_interval_minutes` | `INTEGER` | NOT NULL, default `180` | used by scheduler |
| `last_fetched_at` | `TIMESTAMPTZ` | NULL | |
| `last_fetch_status` | `fetch_status_enum` | NOT NULL, default `never_run` | `never_run, success, partial, failure` |
| `last_fetch_error` | `TEXT` | NULL | last error message, if any |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL | |
| UNIQUE | | `(provider, board_token)` | prevents registering the same board twice |

### 2.7 `jobs`

Normalized job postings, one row per `(job_source_id, external_id)`.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | |
| `job_source_id` | `BIGINT` | NOT NULL, FK → `job_sources.id` ON DELETE CASCADE | |
| `external_id` | `TEXT` | NOT NULL | the job ID/slug as given by the provider |
| `title` | `TEXT` | NOT NULL | |
| `employment_type` | `employment_type_enum` | NOT NULL, default `unknown` | inferred from title/metadata; `unknown` if not inferable |
| `role_category` | `role_category_enum` | NOT NULL, default `other` | inferred via keyword rules; `other` if no rule matches |
| `remote_type` | `remote_type_enum` | NOT NULL, default `unknown` | `onsite, hybrid, remote, unknown` |
| `description_text` | `TEXT` | NOT NULL | plain-text extracted from provider HTML (tags stripped); never rendered as HTML |
| `apply_url` | `TEXT` | NOT NULL | provider-given application URL |
| `canonical_url` | `TEXT` | NOT NULL | normalized URL used for de-duplication/display (scheme lowercased, default ports stripped, tracking query params removed, trailing slash normalized) |
| `content_hash` | `TEXT` | NOT NULL | SHA-256 of normalized `(title, description_text, locations)` — used to detect real content changes vs. no-op refetches |
| `dedupe_key` | `TEXT` | NOT NULL | SHA-256 of `(employer_id, normalized_title, normalized_primary_location)` — catches the same role cross-posted or re-listed with a new `external_id` |
| `posted_at` | `TIMESTAMPTZ` | NULL | provider-reported post date, if given |
| `first_seen_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | first time our system observed this job |
| `last_seen_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | updated every time a fetch still finds this job |
| `is_active` | `BOOLEAN` | NOT NULL, default `true` | set `false` when a fetch no longer returns this job (soft delete; never hard-deleted) |
| `raw_payload` | `JSONB` | NOT NULL | the original provider JSON for this job, for debugging/audit — **treated as untrusted data, never interpolated into queries/HTML** |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL | |
| UNIQUE | | `(job_source_id, external_id)` | source-level duplicate guard |
| INDEX | | `(dedupe_key)` | cross-source duplicate lookup |
| INDEX | | `(is_active, role_category)` | dashboard filtering |

### 2.8 `job_locations`

Greenhouse/Lever/Ashby postings often list multiple office locations for one job. Normalized into
its own table rather than a single text column.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | |
| `job_id` | `BIGINT` | NOT NULL, FK → `jobs.id` ON DELETE CASCADE | |
| `raw_text` | `TEXT` | NOT NULL | as provided |
| `city` | `TEXT` | NULL | parsed best-effort |
| `region` | `TEXT` | NULL | state/province, parsed best-effort |
| `country` | `TEXT` | NULL | parsed best-effort, default `unknown` handled at the service layer, not DB default, since it's inferred |
| `is_remote` | `BOOLEAN` | NOT NULL, default `false` | |
| UNIQUE | | `(job_id, raw_text)` | |

### 2.9 `discovery_runs`

One row per discovery run (manual or scheduled), independent of which sources it touched.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | |
| `trigger_type` | `trigger_type_enum` | NOT NULL | `manual, scheduled` |
| `status` | `run_status_enum` | NOT NULL, default `pending` | `pending, running, succeeded, failed, partial` |
| `started_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | |
| `finished_at` | `TIMESTAMPTZ` | NULL | |
| `sources_attempted` | `INTEGER` | NOT NULL, default `0` | |
| `sources_succeeded` | `INTEGER` | NOT NULL, default `0` | |
| `jobs_created` | `INTEGER` | NOT NULL, default `0` | |
| `jobs_updated` | `INTEGER` | NOT NULL, default `0` | |
| `jobs_deactivated` | `INTEGER` | NOT NULL, default `0` | |
| `error_summary` | `TEXT` | NULL | top-level failure summary if `status = failed` |

### 2.10 `discovery_run_sources`

Per-source detail within a run — this is what lets the UI show "Greenhouse/stripe: 12 found, 2
new" vs. "Lever/acme: timed out" in the same run.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | |
| `discovery_run_id` | `BIGINT` | NOT NULL, FK → `discovery_runs.id` ON DELETE CASCADE | |
| `job_source_id` | `BIGINT` | NOT NULL, FK → `job_sources.id` ON DELETE CASCADE | |
| `status` | `fetch_status_enum` | NOT NULL, default `never_run` | |
| `jobs_found` | `INTEGER` | NOT NULL, default `0` | |
| `jobs_created` | `INTEGER` | NOT NULL, default `0` | |
| `jobs_updated` | `INTEGER` | NOT NULL, default `0` | |
| `error_message` | `TEXT` | NULL | |
| `started_at` | `TIMESTAMPTZ` | NULL | |
| `finished_at` | `TIMESTAMPTZ` | NULL | |
| UNIQUE | | `(discovery_run_id, job_source_id)` | |

### 2.11 `job_candidate_states`

Saved/dismissed state is tracked per candidate (future-proofing for multi-user), not as a column
on `jobs`.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | |
| `job_id` | `BIGINT` | NOT NULL, FK → `jobs.id` ON DELETE CASCADE | |
| `candidate_id` | `BIGINT` | NOT NULL, FK → `candidates.id` ON DELETE CASCADE | |
| `state` | `job_state_enum` | NOT NULL, default `new` | `new, saved, dismissed` (Phase 1 states only; `queued/applied/...` arrive with module 12) |
| `state_reason` | `TEXT` | NULL | optional free-text, e.g. why dismissed |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL | |
| UNIQUE | | `(job_id, candidate_id)` | |

### 2.12 `job_assessments`

Combined, explainable eligibility + match score result for a `(job, candidate)` pair, recomputed
whenever the job or candidate preferences change. Persisted (not computed on every request) so
the dashboard is fast and so there's a record of *why* a score was what it was at the time.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | |
| `job_id` | `BIGINT` | NOT NULL, FK → `jobs.id` ON DELETE CASCADE | |
| `candidate_id` | `BIGINT` | NOT NULL, FK → `candidates.id` ON DELETE CASCADE | |
| `eligibility` | `eligibility_enum` | NOT NULL, default `unknown` | `eligible, ineligible, unknown` |
| `eligibility_reasons` | `JSONB` | NOT NULL, default `[]` | ordered list of `{rule, result, detail}` objects — rendered verbatim in the UI for transparency |
| `match_score` | `SMALLINT` | NOT NULL, CHECK 0–100 | |
| `match_reasons` | `JSONB` | NOT NULL, default `[]` | ordered list of `{factor, weight, contribution, detail}` objects |
| `computed_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | |
| UNIQUE | | `(job_id, candidate_id)` | upserted on recompute |

## 2a. Phase 2.1 tables — resume upload, parsing, verified fact storage

Added for Phase 2 milestone 2.1 (module 1/9 "Verified Fact Vault" + module 7 "Resume Tailoring"
prerequisites). Migration: `alembic/versions/6503438e5cd3_add_resumes_and_candidate_facts.py`.

### 2a.1 `resumes`

One row per uploaded resume file. **Immutable by construction**: no update/delete endpoint
exists for this table or the files it references — the only writes are the initial `INSERT` at
upload time and the one-time `parse_status`/`parse_error` set during that same request. This is
how "maintain an immutable copy of the original resume" is enforced: not by convention, but by
the absence of any code path that could mutate a row after creation.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | |
| `candidate_id` | `BIGINT` | NOT NULL, FK → `candidates.id` ON DELETE CASCADE | |
| `original_filename` | `TEXT` | NOT NULL | client-supplied name, display only — never used to build a filesystem path |
| `file_format` | `resume_file_format_enum` | NOT NULL | `pdf, docx` |
| `storage_path` | `TEXT` | NOT NULL | path under `resume_storage_dir` (gitignored, see `.gitignore` `backend/storage/`); filename is the SHA-256 checksum + extension, never the client-supplied name, to eliminate path-traversal risk |
| `file_size_bytes` | `BIGINT` | NOT NULL | |
| `sha256_checksum` | `TEXT` | NOT NULL | content hash; re-uploading identical bytes reuses the same stored file |
| `parse_status` | `resume_parse_status_enum` | NOT NULL, default `pending` | `pending, success, partial, failed` — `partial` means at least one extracted fact fell back to `FactType.OTHER` (headers not fully recognized), `failed` means text extraction itself raised |
| `parse_error` | `TEXT` | NULL | human-readable extraction failure detail, set only when `parse_status = failed` |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL | |

### 2a.2 `candidate_facts`

A verified-fact row extracted from a resume (or, later, entered manually). This is the concrete
implementation of the "generalized fact vault" sketched in the old §5 below, scoped for Phase
2.1 to resume-derived facts only.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | |
| `candidate_id` | `BIGINT` | NOT NULL, FK → `candidates.id` ON DELETE CASCADE | |
| `resume_id` | `BIGINT` | NULL, FK → `resumes.id` ON DELETE CASCADE | null reserved for future non-resume-sourced facts (e.g. manual entry) |
| `fact_type` | `fact_type_enum` | NOT NULL | `education, skill, project, work_experience, achievement, other` — `other` is the explicit, non-fabricating fallback bucket used when section headers aren't recognized |
| `fact_key` | `TEXT` | NOT NULL | short label, e.g. institution name, employer name, skill category |
| `fact_value` | `JSONB` | NOT NULL | structured payload, shape varies by `fact_type` (e.g. `{bullets: [...], dates_text: "..."}` for work experience; `{items: [...]}` for skills) |
| `raw_text` | `TEXT` | NULL | the verbatim source block this fact was parsed from, kept for human review/audit — never discarded even after the structured fields are extracted |
| `source` | `fact_source_enum` | NOT NULL, default `resume_extraction` | `resume_extraction, manual_entry` |
| `verification_status` | `fact_verification_status_enum` | NOT NULL, default `unverified` | `unverified, verified, edited, rejected` — see note below on why this replaces a numeric confidence score |
| `verified_at` | `TIMESTAMPTZ` | NULL | set whenever `verification_status` changes away from its current value |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL | |

**Deviation from the original §5 sketch, intentional:** the original sketch below lists a numeric
`confidence` column. Phase 2.1 omits it in favor of `verification_status`, an explicit human
review state machine (`unverified → verified | edited | rejected`). A numeric confidence score
implies a precision the deterministic section parser doesn't actually have, and risks being
treated as "good enough, don't bother reviewing" past some threshold — which conflicts directly
with "never fabricate experience/qualifications" and "use AI for language improvements... not for
inventing facts." Requiring an explicit human action instead keeps the uncertainty honest.

**Dates are never parsed into a real `DATE`.** `fact_value.dates_text`, when present, is the
verbatim matched substring (e.g. `"Sep 2021 - Jun 2025"`) — never coerced into a `date` object,
since doing so would assert a precision (exact day) the source resume text doesn't actually give.
This mirrors the existing `graduation_date_precision` pattern on `candidates`.

## 3. Enum reference

| Enum | Values |
|---|---|
| `degree_level_enum` | `associate, bachelors, masters, phd, bootcamp, other, unknown` |
| `date_precision_enum` | `exact, month, unknown` |
| `work_auth_status_enum` | `us_citizen, permanent_resident, visa_holder, requires_sponsorship, unknown` |
| `tri_state_enum` | `yes, no, unknown` |
| `employment_type_enum` | `internship, new_grad, full_time, contract, unknown` |
| `location_pref_type_enum` | `state, metro, remote` |
| `role_category_enum` | `swe_backend, swe_frontend, swe_fullstack, infrastructure, ai_engineering, cybersecurity, qa, it_support, other` |
| `job_provider_enum` | `greenhouse, lever, ashby` |
| `fetch_status_enum` | `never_run, success, partial, failure` |
| `remote_type_enum` | `onsite, hybrid, remote, unknown` |
| `trigger_type_enum` | `manual, scheduled` |
| `run_status_enum` | `pending, running, succeeded, failed, partial` |
| `job_state_enum` | `new, saved, dismissed` |
| `eligibility_enum` | `eligible, ineligible, unknown` |
| `resume_file_format_enum` | `pdf, docx` |
| `resume_parse_status_enum` | `pending, success, partial, failed` |
| `fact_type_enum` | `education, skill, project, work_experience, achievement, other` |
| `fact_source_enum` | `resume_extraction, manual_entry` |
| `fact_verification_status_enum` | `unverified, verified, edited, rejected` |

## 4. Deduplication strategy (module 4)

Two layers, both implemented in Phase 1:

1. **Source-level**: `UNIQUE (job_source_id, external_id)`. Re-fetching the same board never
   creates a second row for the same provider-assigned job ID; it updates `last_seen_at` and, if
   `content_hash` changed, updates the mutable fields and bumps `updated_at`.
2. **Cross-source / re-listing**: `dedupe_key = sha256(employer_id | normalized_title |
   normalized_primary_location)`. When a new `(job_source_id, external_id)` row would be created
   with a `dedupe_key` that already exists and is `is_active = true`, the discovery service links
   it as a duplicate rather than creating a second visible job (Phase 1: the second row is still
   stored for audit but excluded from the default dashboard query via a `duplicate_of_job_id`
   nullable self-FK on `jobs` — see migration for exact nullable column — and is never shown as a
   separate card).

URL normalization (used for `canonical_url` and indirectly for dedupe) lower-cases the scheme and
host, strips default ports, strips known tracking query params (`utm_*`, `gh_src`, `lever-source`,
etc.), and removes trailing slashes.

## 5. Future (not migrated yet)

Documented here so existing tables are designed to not conflict with them later — **no migration
for these exists yet**:

- `candidate_facts` sourced from `manual_entry` (screening-question answers not derived from a
  resume) — the table and `source` enum value already exist (§2a.2) and support this; only the
  manual-entry UI/endpoint is not built yet (module 9).
- `resume_versions` — job-specific tailored variants of a base `resumes` row, with a diff against
  the original and generated DOCX/PDF file references (module 7, Phase 2 milestones 2.3/2.4).
  `resumes`/`candidate_facts` themselves are now implemented — see §2a.
- `ai_provider_configs` — provider name, mode (`cloud/local/mock`), model, endpoint, active flag
  (module 8, Phase 2 milestone 2.2).
- `application_answers` — reusable Q&A pairs with a `requires_human_review` flag (module 9).
- `applications` — the submission queue/state machine (module 12): `state` enum including
  `blocked_pending_review`, `authorized`, `submitted`, `confirmed`, `failed`, etc.
- `application_events` — append-only state-transition audit trail for `applications` (module 12/15).
- `submission_policies`, `platform_authorizations`, `daily_submission_counters` — the
  Authorization Policy Engine and its daily-limit/emergency-pause enforcement (module 11).
- `notifications` — module 14.
- `audit_logs` — general security/privacy audit trail (module 15), separate from
  `application_events` since it covers more than submissions (e.g., credential access, profile
  edits).
