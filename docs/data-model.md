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

One row per uploaded resume file. **File bytes are write-once**: no PATCH/PUT exists for
`original_filename` / `storage_path` / checksum / size / format. The only in-place writes after
upload are `parse_status` / `parse_error` (upload + reprocess) and `is_primary` (first upload,
explicit "set primary", or replacement when the primary file is deleted). An explicit
`DELETE /api/resumes/{id}` removes that row and its resume-specific extracted records; it does
not touch jobs, preferences, or saved jobs.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | |
| `candidate_id` | `BIGINT` | NOT NULL, FK → `candidates.id` ON DELETE CASCADE | |
| `original_filename` | `TEXT` | NOT NULL | client-supplied name, display only — never used to build a filesystem path |
| `file_format` | `resume_file_format_enum` | NOT NULL | `pdf, docx` |
| `storage_path` | `TEXT` | NOT NULL | path under `resume_storage_dir` (gitignored, see `.gitignore` `backend/storage/`); filename is the SHA-256 checksum + extension, never the client-supplied name, to eliminate path-traversal risk |
| `file_size_bytes` | `BIGINT` | NOT NULL | |
| `sha256_checksum` | `TEXT` | NOT NULL | content hash; re-uploading identical bytes for the same candidate returns the existing resume (no second row, no re-parse) |
| `parse_status` | `resume_parse_status_enum` | NOT NULL, default `pending` | `pending, success, partial, failed` — `partial` means at least one extracted fact fell back to `FactType.OTHER` (headers not fully recognized), `failed` means text extraction itself raised |
| `parse_error` | `TEXT` | NULL | human-readable extraction failure detail, set only when `parse_status = failed` |
| `is_primary` | `BOOLEAN` | NOT NULL, default `false` | exactly one default resume per candidate (partial unique index). |
| `profile_name` | `TEXT` | NOT NULL | display name; file bytes stay write-once |
| `profile_description` | `TEXT` | NOT NULL | |
| `category` | `resume_category_enum` | NOT NULL, default `custom` | `general_swe, backend, fullstack, ai_ml, custom` |
| `is_approved` | `BOOLEAN` | NOT NULL, default `false` | only approved, non-archived profiles are auto-selected |
| `is_archived` | `BOOLEAN` | NOT NULL, default `false` | |
| `focus_areas` | `JSONB` | NOT NULL | list of strings used for ranking |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL | |

### 2a.2 `candidate_facts`

A verified-fact row extracted from a resume (or, later, entered manually). This is the concrete
implementation of the "generalized fact vault" sketched in the old §5 below, scoped for Phase
2.1 to resume-derived facts only.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | |
| `candidate_id` | `BIGINT` | NOT NULL, FK → `candidates.id` ON DELETE CASCADE | |
| `resume_id` | `BIGINT` | NULL, FK → `resumes.id` ON DELETE SET NULL | null for independently kept facts (verified/edited rows detached when their source resume is deleted, or future manual entry) |
| `fact_type` | `fact_type_enum` | NOT NULL | `education, skill, project, work_experience, achievement, other` — `other` is the explicit, non-fabricating fallback bucket used when section headers aren't recognized |
| `fact_key` | `TEXT` | NOT NULL | short label, e.g. institution name, employer name, skill category |
| `fact_value` | `JSONB` | NOT NULL | structured payload, shape varies by `fact_type`. Education: `{institution, location, degree, major, gpa, dates_text, coursework, bullets, raw_block}`. Work: `{employer, position, location, dates_text, bullets, unclassified_text, raw_block}`. Project: `{name, tagline, technologies, dates_text, bullets, raw_block}`. Skill: `{items: [...]}` (one fact per category, key = category name). Achievement: `{organization?, text, bullets}`; other: `{text}`. Fields the source text does not contain are `null` — never fabricated. Any type may also carry parser review flags: `needs_review` (bool), `review_reasons` (string[]), `ambiguous_fields` (string[]), and `possible_duplicate_of` (fact id) when an updated upload conflicts with an already-reviewed record. Flagged facts cannot be bulk-verified. |
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

## 2b. Phase 2.2 tables — canonical candidate knowledge base

The extracted `candidate_facts` table (§2a.2) stays the resume-scoped, traceable
record. `canonical_facts` is the independent, authoritative profile future
application automation will read. A canonical row has **no required resume
foreign key**; deleting an uploaded resume cannot cascade onto it.

Migration: `alembic/versions/a1b2c3d4e5f6_add_canonical_facts.py`.

### 2b.1 `canonical_facts`

One authoritative version of one fact (school, job, project, skill group, …).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | |
| `candidate_id` | `BIGINT` | NOT NULL, FK → `candidates.id` ON DELETE CASCADE | |
| `fact_type` | `fact_type_enum` | NOT NULL | same categories as extracted facts |
| `fact_key` | `TEXT` | NOT NULL | display label |
| `fact_value` | `JSONB` | NOT NULL | same payload shapes as §2a.2 |
| `identity_key` | `TEXT` | NOT NULL | `fact_type\|normalized_key` — one *active* row per identity |
| `content_fingerprint` | `TEXT` | NOT NULL | exact-content hash (review metadata stripped) used to skip re-imports |
| `status` | `canonical_fact_status_enum` | NOT NULL, default `active` | `active, conflict, archived` |
| `verification_status` | `fact_verification_status_enum` | NOT NULL, default `unverified` | imported from a verified extracted fact starts `verified`; manual entries start `unverified`. Never auto-verified. |
| `verified_at` | `TIMESTAMPTZ` | NULL | |
| `needs_review` | `BOOLEAN` | NOT NULL, default `false` | true for conflict rows and flagged imports |
| `review_reasons` | `JSONB` | NOT NULL, default `[]` | |
| `conflicts_with_id` | `BIGINT` | NULL, FK → `canonical_facts.id` ON DELETE SET NULL | set on `status=conflict` rows; points at the active fact they disagree with |
| `archived_at` | `TIMESTAMPTZ` | NULL | set when status becomes `archived` |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL | |
| UNIQUE | | `(candidate_id, identity_key) WHERE status = 'active'` | one authoritative version |

A same-identity import whose content differs from the active row becomes a new
`status=conflict` row. The active value is never overwritten.

### 2b.2 `canonical_fact_sources`

Provenance: which extracted record, resume, or user action supplied a canonical
fact. Multiple sources can point at one canonical row (the same job imported
from two resumes).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BIGSERIAL` | PK | |
| `canonical_fact_id` | `BIGINT` | NOT NULL, FK → `canonical_facts.id` ON DELETE CASCADE | |
| `candidate_fact_id` | `BIGINT` | NULL, FK → `candidate_facts.id` ON DELETE SET NULL | the extracted record, if any |
| `resume_id` | `BIGINT` | NULL, FK → `resumes.id` ON DELETE SET NULL | which file proposed it |
| `origin` | `canonical_fact_origin_enum` | NOT NULL | `resume_import, manual_entry, profile` |
| `note` | `TEXT` | NULL | |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL | |
| UNIQUE | | `(candidate_fact_id) WHERE candidate_fact_id IS NOT NULL` | one extracted record maps to at most one canonical fact |

Work authorization, sponsorship, and graduation date stay on `candidates`
(§2.1). They remain the eligibility source of truth. `origin=profile` is reserved
for later linking of those fields into the knowledge base; this migration does
not move them.

## 2c. Phase 2.2.1 tables — writing style

Stylistic preferences and samples are independent of qualifications. Samples
are never treated as verified facts.

Migration: `alembic/versions/c3d4e5f6a7b8_add_writing_style_profile.py`.

### 2c.1 `writing_style_profiles`

One row per candidate. Created with editable defaults on first read.

| Column | Type | Notes |
|---|---|---|
| `candidate_id` | `BIGINT` UNIQUE FK → `candidates.id` ON DELETE CASCADE | |
| `tone` | `writing_tone_enum` | default `professional_conversational` |
| `formality` | `writing_formality_enum` | default `medium` |
| `preferred_length` | `writing_length_enum` | default `short_medium` |
| `sentence_complexity` | `writing_complexity_enum` | default `moderate` |
| `technical_detail` | `writing_technical_detail_enum` | default `specific` |
| `vocabulary` | `writing_vocabulary_enum` | default `straightforward` |
| `phrases_to_avoid` | `JSONB` | list of strings |
| `additional_instructions` | `TEXT` | free-form, editable |

### 2c.2 `writing_samples`

Authentic writing examples. Separate from `canonical_facts` and
`application_answers`. An AI draft is never stored here unless the candidate
explicitly adopts it (`origin=adopted_from_answer`).

| Column | Type | Notes |
|---|---|---|
| `candidate_id` | `BIGINT` FK → `candidates.id` ON DELETE CASCADE | |
| `body` | `TEXT` | 20–4000 characters |
| `content_fingerprint` | `TEXT` | unique with candidate_id |
| `category` | `writing_sample_category_enum` | technical_experience, motivation, general, other |
| `origin` | `writing_sample_origin_enum` | `user_written` or `adopted_from_answer` only |
| `is_approved_style_reference` | `BOOLEAN` | generation uses approved samples only |
| `source_answer_id` | `BIGINT` NULL FK → `application_answers.id` ON DELETE SET NULL | |

## 2d. Phase 2.3 tables — application preparation

Job-specific review material. A preparation is never a submission. The
original `resumes` row is referenced but never modified.

Migration: `alembic/versions/f6a7b8c9d0e1_add_application_preparations.py`.

### 2d.1 `application_preparations`

One open row per `(candidate_id, job_id)` while `state` is
`preparing`, `needs_review`, `ready`, or `failed`. Cancelled rows stay
for history. Failed rows are kept and reused, not replaced.

| Column | Type | Notes |
|---|---|---|
| `candidate_id` | `BIGINT` FK → `candidates.id` ON DELETE CASCADE | |
| `job_id` | `BIGINT` NULL FK → `jobs.id` ON DELETE SET NULL | listing may disappear later |
| `source_resume_id` | `BIGINT` NULL FK → `resumes.id` ON DELETE SET NULL | selected profile; original file is downloaded unchanged |
| `resume_selection_reason` | `TEXT` | why this profile was chosen |
| `resume_selection_source` | `resume_selection_source_enum` | automatic / manual / fallback_default / none |
| `state` | `preparation_state_enum` | preparation progress only |
| `snapshot_job_title` | `TEXT` | frozen at create time |
| `snapshot_employer` | `TEXT` | |
| `snapshot_description` | `TEXT` | full JD used for analysis |
| `snapshot_apply_url` | `TEXT` | |
| `snapshot_content_hash` | `TEXT` | listing hash at create time |
| `analysis` | `JSONB` | stated vs inferred requirements |
| `match_report` | `JSONB` | matched / missing / uncertain |
| `tailored_resume` | `JSONB` | reordered verified facts only |
| `tailored_resume_status` | `preparation_item_status_enum` | |
| `design_limitation` | `TEXT` | records that original visual design is not reproduced |
| `error_message` | `TEXT` | failed preparations keep this |
| `docx_path` | `TEXT` NULL | under `storage/preparations/` |
| `pdf_path` | `TEXT` NULL | |

Partial unique index `uq_application_preparations_open` on
`(candidate_id, job_id)` where state is open and `job_id` is not null.

### 2d.2 `application_preparation_answers`

Drafts for this job only. Approved library answers may be copied or
adapted; the library row is never overwritten.

| Column | Type | Notes |
|---|---|---|
| `preparation_id` | `BIGINT` FK → `application_preparations.id` ON DELETE CASCADE | |
| `question` | `TEXT` | unique with preparation_id |
| `answer_text` | `TEXT` | empty for sensitive questions until review |
| `category` | `answer_category_enum` | |
| `origin` | `preparation_answer_origin_enum` | reused / adapted / generated |
| `status` | `preparation_item_status_enum` | |
| `source_answer_id` | `BIGINT` NULL FK → `application_answers.id` ON DELETE SET NULL | |
| `is_sensitive` | `BOOLEAN` | |
| `canonical_fact_ids` | `JSONB` | facts cited for this draft |
| `unsupported_claims` | `JSONB` | |
| `missing_information` | `JSONB` | |

## 2e. Phase 2.5.2 table — tracked applications

One row per `(candidate_id, job_id)` for the life of that application.
The row stores status and short notes. It does not store answers,
credentials, email addresses, or phone numbers. Confirmation and
failure text are redacted when they contain an email or a long number.

Migration: `alembic/versions/i9d0e1f2a3b4_add_tracked_applications.py`.

| Column | Type | Notes |
|---|---|---|
| `candidate_id` | `BIGINT` FK → `candidates.id` ON DELETE CASCADE | |
| `job_id` | `BIGINT` FK → `jobs.id` ON DELETE RESTRICT | unique with candidate_id |
| `employer` | `TEXT` | employer name snapshot |
| `preparation_id` | `BIGINT` NULL FK → `application_preparations.id` ON DELETE SET NULL | |
| `resume_id` | `BIGINT` NULL FK → `resumes.id` ON DELETE SET NULL | selected resume id only |
| `status` | `application_status_enum` | see below |
| `submitted_at` | `TIMESTAMPTZ` NULL | set only when status becomes submitted |
| `confirmation` | `TEXT` NULL | employer confirmation text, redacted |
| `failure_reason` | `TEXT` NULL | readiness or failure summary, redacted |
| `resubmit_after` | `TIMESTAMPTZ` NULL | set when the user records that a submission was not received; a later submit requires a browser session opened after this time |

## 2f. Phase 2.5.4 table — application events

Append-only status changes for one tracked application. The reason is a
short redacted summary. The table does not store answers, credentials,
or contact details.

Migration: `alembic/versions/j0e1f2a3b4c5_add_application_events.py`.

| Column | Type | Notes |
|---|---|---|
| `application_id` | `BIGINT` FK → `tracked_applications.id` ON DELETE CASCADE | |
| `previous_status` | `application_status_enum` | status before the change |
| `new_status` | `application_status_enum` | status after the change |
| `reason` | `TEXT` NULL | confirmation or failure summary, redacted |
| `source` | `application_event_source_enum` | `browser` or `manual` |
| `created_at` | `TIMESTAMPTZ` | when the change was recorded |

Allowed moves: `preparing` ↔ `needs_review` ↔ `ready_to_submit`;
`ready_to_submit` → `submitting` only from an authorized submission;
`submitting` → `submitted`, `submission_failed`, or `confirmation_unknown`.
`submitted` is terminal. `confirmation_unknown` can be corrected to
`submitted` or `submission_failed`, and cannot return to `submitting`.
Readiness writes only `needs_review` or `ready_to_submit`, and it does
not change a row that is `submitting`, `submitted`, or `confirmation_unknown`.
A failed pre-submit check moves `ready_to_submit` back to `needs_review`
without a click. `submitted` is stored only when the employer page shows
a receipt, or when the user records that they saw one. A not-received
correction sets `resubmit_after`. The next submit has to come from a
browser session opened after that time, after a new readiness check and
a new confirmation.

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
| `canonical_fact_status_enum` | `active, conflict, archived` |
| `canonical_fact_origin_enum` | `resume_import, manual_entry, profile` |
| `preparation_state_enum` | `preparing, needs_review, ready, failed, cancelled` |
| `application_status_enum` | `preparing, needs_review, ready_to_submit, submitting, submitted, submission_failed, confirmation_unknown` |
| `application_event_source_enum` | `browser, manual` |
| `preparation_answer_origin_enum` | `reused, adapted, generated` |
| `preparation_item_status_enum` | `draft, approved, rejected, needs_review` |
| `resume_category_enum` | `general_swe, backend, fullstack, ai_ml, custom` |
| `resume_selection_source_enum` | `automatic, manual, fallback_default, none` |

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

- `canonical_facts` / `canonical_fact_sources` — **implemented** (Phase 2.2); see §2b.
- `candidate_facts` sourced from `manual_entry` — the extracted-fact table still supports this
  (`source` enum); the knowledge-base manual-entry path writes `canonical_facts` with
  `origin=manual_entry` instead.
- `application_preparations` / `application_preparation_answers` — **implemented** (Phase 2.3);
  see §2d.
- `resume_versions` — superseded for 2.3 by `application_preparations.tailored_resume`.
  Job-specific visual template cloning remains later if needed.
- `ai_provider_configs` — not a table. Phase 2.2 uses env settings (`AI_ENABLED`,
  `AI_PROVIDER`, `GEMINI_API_KEY`, model/temperature) plus `GET /api/ai/status`.
- `application_answers` / `application_answer_facts` — **implemented** (Phase 2.2).
  Reusable Q&A, independent of resumes. Equivalent (fingerprint + answer text) is unique.
  At most one preferred answer per question. Sensitive categories cannot skip `reviewed`.
  Grounded AI drafts use verified canonical facts and never persist on provider failure.
- `tracked_applications` — **implemented** (Phase 2.5.2); see §2e. One row
  per candidate and job.
- `application_events` — **implemented** for tracked applications (Phase 2.5.4); see §2f.
- `applications` — the fuller submission queue/state machine (module 12) remains
  future. 2.5.4 does not add `blocked_pending_review`.
- `submission_policies`, `platform_authorizations`, `daily_submission_counters` — the
  Authorization Policy Engine and its daily-limit/emergency-pause enforcement (module 11).
- `notifications` — module 14.
- `audit_logs` — general security/privacy audit trail (module 15), separate from
  `application_events` since it covers more than submissions (e.g., credential access, profile
  edits).
