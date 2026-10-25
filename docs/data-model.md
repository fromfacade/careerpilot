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
| `base_resume_filename` | `TEXT` | NULL | reserved for Phase 2 resume module; not used in Phase 1 |
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

## 5. Future (not migrated in Phase 1)

Documented here so Phase 1 tables are designed to not conflict with them later — **no migration
for these exists yet**:

- `candidate_facts` — generalized verified-fact vault: `(candidate_id, fact_key, fact_value,
  source, confidence, verified_at)` for arbitrary screening-question answers (module 1/9).
- `resumes`, `resume_versions` — base resume + tailored variants per job, with generated DOCX/PDF
  file references (module 7).
- `ai_provider_configs` — provider name, mode (`cloud/local/mock`), model, endpoint, active flag
  (module 8).
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
