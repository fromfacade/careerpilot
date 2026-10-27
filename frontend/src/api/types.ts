// Types mirror backend/app/schemas/*.py exactly. Keep in sync by hand for
// Phase 1 (no codegen yet) — see docs/data-model.md for the enum source of
// truth.

export type DegreeLevel = 'associate' | 'bachelors' | 'masters' | 'phd' | 'bootcamp' | 'other' | 'unknown';
export type DatePrecision = 'exact' | 'month' | 'unknown';
export type WorkAuthStatus = 'us_citizen' | 'permanent_resident' | 'visa_holder' | 'requires_sponsorship' | 'unknown';
export type TriState = 'yes' | 'no' | 'unknown';
export type EmploymentType = 'internship' | 'new_grad' | 'full_time' | 'contract' | 'unknown';
export type LocationPreferenceType = 'state' | 'metro' | 'remote';
export type RoleCategory =
  | 'swe_backend'
  | 'swe_frontend'
  | 'swe_fullstack'
  | 'infrastructure'
  | 'ai_engineering'
  | 'cybersecurity'
  | 'qa'
  | 'it_support'
  | 'other';
export type JobProvider = 'greenhouse' | 'lever' | 'ashby';
export type FetchStatus = 'never_run' | 'success' | 'partial' | 'failure';
export type RemoteType = 'onsite' | 'hybrid' | 'remote' | 'unknown';
export type TriggerType = 'manual' | 'scheduled';
export type RunStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'partial';
export type JobState = 'new' | 'saved' | 'dismissed';
export type Eligibility = 'eligible' | 'ineligible' | 'unknown';
// Deliberately separate from Eligibility (hard requirements) and from
// match_score (numeric alignment) -- see docs/architecture.md §6. A job can
// be `eligible` (no visa/timing blocker) and still `not_relevant` (e.g. a
// non-technical or director-level posting); the UI must never conflate
// these two.
export type Relevance = 'relevant' | 'not_relevant' | 'unknown';
export type SeniorityLevel =
  | 'entry'
  | 'senior'
  | 'staff_or_principal'
  | 'manager_or_director'
  | 'executive'
  | 'unknown';
// Query-param-only, never persisted -- see backend JobSort/JobView.
export type JobSort =
  | 'score_desc'
  | 'score_asc'
  | 'most_eligible_first'
  | 'newest_first'
  | 'oldest_first'
  | 'company_asc'
  | 'company_desc';
export type JobView = 'recommended' | 'all';

// --- Phase 2.1: resume upload, parsing, and verified fact storage ---
export type ResumeFileFormat = 'pdf' | 'docx';
// `failed` means text extraction itself raised (corrupt/unreadable file) --
// the upload is still persisted (immutable), just with zero facts. See
// docs/architecture.md §6b.
export type ResumeParseStatus = 'pending' | 'success' | 'partial' | 'failed';
export type FactType = 'education' | 'skill' | 'project' | 'work_experience' | 'achievement' | 'other';
export type FactSource = 'resume_extraction' | 'manual_entry';
// Deliberately no numeric confidence score -- an explicit human review
// state machine instead. 'unverified' is the only initial state and can
// never be set again via the API once left -- see CandidateFactUpdateInput.
export type FactVerificationStatus = 'unverified' | 'verified' | 'edited' | 'rejected';

export interface Candidate {
  id: number;
  full_name: string;
  email: string;
  phone: string | null;
  school: string | null;
  degree_level: DegreeLevel;
  major: string | null;
  graduation_date: string | null;
  graduation_date_precision: DatePrecision;
  work_authorization_status: WorkAuthStatus;
  requires_sponsorship: TriState;
  current_location: string | null;
  linkedin_url: string | null;
  github_url: string | null;
  portfolio_url: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export type CandidateInput = Omit<Candidate, 'id' | 'created_at' | 'updated_at'>;

export interface LocationPreference {
  id?: number;
  label: string;
  location_type: LocationPreferenceType;
  priority: number;
}

export interface RolePreference {
  id?: number;
  role_category: RoleCategory;
  priority: number;
}

export interface Preferences {
  remote_ok: boolean;
  target_employment_types: EmploymentType[];
  target_start_window_start: string | null;
  target_start_window_end: string | null;
  min_match_score_to_surface: number;
  locations: LocationPreference[];
  roles: RolePreference[];
}

export interface JobSource {
  id: number;
  employer_id: number;
  employer_name: string;
  provider: JobProvider;
  board_token: string;
  is_enabled: boolean;
  fetch_interval_minutes: number;
  last_fetched_at: string | null;
  last_fetch_status: FetchStatus;
  last_fetch_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobSourceInput {
  employer_name: string;
  provider: JobProvider;
  board_token: string;
  is_enabled?: boolean;
  fetch_interval_minutes?: number;
}

export interface JobLocation {
  raw_text: string;
  city: string | null;
  region: string | null;
  country: string | null;
  is_remote: boolean;
}

export interface MatchReason {
  factor?: string;
  rule?: string;
  weight?: number;
  contribution?: number;
  result?: string;
  detail: string;
}

export interface JobAssessment {
  eligibility: Eligibility;
  eligibility_reasons: MatchReason[];
  relevance: Relevance;
  relevance_reasons: MatchReason[];
  match_score: number;
  match_reasons: MatchReason[];
  computed_at: string;
}

export interface Job {
  id: number;
  employer_name: string;
  provider: JobProvider;
  title: string;
  employment_type: EmploymentType;
  role_category: RoleCategory;
  remote_type: RemoteType;
  seniority_level: SeniorityLevel;
  is_non_technical: boolean;
  description_text: string;
  apply_url: string;
  canonical_url: string;
  posted_at: string | null;
  first_seen_at: string;
  last_seen_at: string;
  is_active: boolean;
  locations: JobLocation[];
  state: JobState;
  assessment: JobAssessment | null;
}

export interface DiscoveryRunSource {
  job_source_id: number;
  provider: JobProvider;
  board_token: string;
  employer_name: string;
  status: FetchStatus;
  jobs_found: number;
  jobs_created: number;
  jobs_updated: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface DiscoveryRun {
  id: number;
  trigger_type: TriggerType;
  status: RunStatus;
  started_at: string;
  finished_at: string | null;
  sources_attempted: number;
  sources_succeeded: number;
  jobs_created: number;
  jobs_updated: number;
  jobs_deactivated: number;
  error_summary: string | null;
  sources: DiscoveryRunSource[];
}

export interface SchedulerStatus {
  enabled: boolean;
  interval_minutes: number;
  running: boolean;
}

/** Display-only filters for `GET /api/jobs` -- never deletes/hides jobs
 * from the database, only from a given query's result set. */
export interface ListJobsParams {
  view?: JobView;
  states?: JobState[];
  include_inactive?: boolean;
  min_score?: number;
  role_categories?: RoleCategory[];
  employment_types?: EmploymentType[];
  remote_types?: RemoteType[];
  eligibility?: Eligibility[];
  relevance?: Relevance[];
  companies?: string[];
  location?: string;
  posted_within_days?: number;
  sort?: JobSort;
  limit?: number;
  offset?: number;
}

export interface ListJobsResult {
  jobs: Job[];
  /** Count across the *entire* filtered result set, not just this page --
   * read from the `X-Total-Count` response header. */
  total: number;
}

export interface Resume {
  id: number;
  candidate_id: number;
  original_filename: string;
  file_format: ResumeFileFormat;
  file_size_bytes: number;
  sha256_checksum: string;
  parse_status: ResumeParseStatus;
  parse_error: string | null;
  is_primary: boolean;
  created_at: string;
}

export interface ResumeUploadResult {
  resume: Resume;
  facts_extracted: number;
  /** Extracted records skipped because an identical one was already verified/edited. */
  facts_skipped_duplicate: number;
  /** True when a byte-identical file was uploaded before; nothing new was parsed. */
  already_uploaded: boolean;
}

export interface ResumeReprocessResult {
  resume: Resume;
  facts_extracted: number;
  facts_replaced: number;
  facts_preserved: number;
  facts_skipped_duplicate: number;
}

export interface ResumeDeleteInput {
  delete_verified_facts?: boolean;
  replacement_resume_id?: number | null;
}

export interface ResumeDeleteResult {
  deleted_resume_id: number;
  facts_deleted: number;
  facts_preserved: number;
  primary_resume_id: number | null;
}

/** Shape varies by `fact_type`. Fields are omitted (null) when the
 * parser could not find them -- never fabricated.
 * - education: `{ institution, location, degree, major, gpa, dates_text, coursework, bullets, raw_block }`
 * - work_experience: `{ employer, position, location, dates_text, bullets, unclassified_text, raw_block }`
 * - project: `{ name, tagline, technologies, dates_text, bullets, raw_block }`
 * - skill: `{ items: string[] }`
 * - achievement: `{ organization?, text, bullets }`; other: `{ text: string }`
 *
 * Any type may also carry the parser's review flags (see `resume/reviewPolicy.ts`):
 * `needs_review`, `review_reasons`, `ambiguous_fields`, and, when an updated
 * upload conflicts with an already-reviewed record, `possible_duplicate_of`. */
export type FactValue = Record<string, unknown>;

export interface CandidateFact {
  id: number;
  candidate_id: number;
  resume_id: number | null;
  fact_type: FactType;
  fact_key: string;
  fact_value: FactValue;
  raw_text: string | null;
  source: FactSource;
  verification_status: FactVerificationStatus;
  verified_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CandidateFactUpdateInput {
  fact_key?: string;
  fact_value?: FactValue;
  verification_status?: Exclude<FactVerificationStatus, 'unverified'>;
}

export interface CandidateFactBulkUpdateInput {
  fact_ids: number[];
  verification_status: Exclude<FactVerificationStatus, 'unverified'>;
}

export interface ListCandidateFactsParams {
  fact_type?: FactType;
  verification_status?: FactVerificationStatus;
}

export type CanonicalFactStatus = 'active' | 'conflict' | 'archived';
export type CanonicalFactOrigin = 'resume_import' | 'manual_entry' | 'profile';

export interface CanonicalFactSource {
  id: number;
  canonical_fact_id: number;
  candidate_fact_id: number | null;
  resume_id: number | null;
  origin: CanonicalFactOrigin;
  note: string | null;
  created_at: string;
}

export interface CanonicalFact {
  id: number;
  candidate_id: number;
  fact_type: FactType;
  fact_key: string;
  fact_value: FactValue;
  identity_key: string;
  status: CanonicalFactStatus;
  verification_status: FactVerificationStatus;
  verified_at: string | null;
  needs_review: boolean;
  review_reasons: unknown[];
  conflicts_with_id: number | null;
  archived_at: string | null;
  sources: CanonicalFactSource[];
  created_at: string;
  updated_at: string;
}

export interface CanonicalFactImportResult {
  created: number;
  linked: number;
  conflicts: number;
  skipped: number;
  facts: CanonicalFact[];
}

export type AnswerCategory =
  | 'interest'
  | 'experience'
  | 'skills'
  | 'logistics'
  | 'work_authorization'
  | 'sponsorship'
  | 'disability'
  | 'veteran'
  | 'demographic'
  | 'criminal_history'
  | 'legal_attestation'
  | 'salary'
  | 'other';

export type AnswerStatus = 'draft' | 'reviewed' | 'approved';
export type AnswerOrigin = 'manual' | 'ai_draft';

export interface ApplicationAnswer {
  id: number;
  candidate_id: number;
  question: string;
  question_fingerprint: string;
  answer_text: string;
  category: AnswerCategory;
  status: AnswerStatus;
  origin: AnswerOrigin;
  is_reusable: boolean;
  is_preferred: boolean;
  is_sensitive: boolean;
  prefer_not_to_answer: boolean;
  missing_information: unknown[];
  generation_metadata: Record<string, unknown>;
  rewritten_from_id: number | null;
  unsupported_claims: unknown[];
  fact_links: { id: number; canonical_fact_id: number | null }[];
  created_at: string;
  updated_at: string;
}

export type WritingTone = 'professional' | 'conversational' | 'formal' | 'professional_conversational';
export type WritingFormality = 'low' | 'medium' | 'high';
export type WritingLength = 'short' | 'short_medium' | 'medium' | 'long';
export type WritingComplexity = 'simple' | 'moderate' | 'varied';
export type WritingTechnicalDetail = 'low' | 'moderate' | 'specific' | 'high';
export type WritingVocabulary = 'straightforward' | 'technical' | 'mixed';
export type WritingSampleCategory = 'technical_experience' | 'motivation' | 'general' | 'other';
export type WritingSampleOrigin = 'user_written' | 'adopted_from_answer';

export interface WritingStyleProfile {
  id: number;
  candidate_id: number;
  tone: WritingTone;
  formality: WritingFormality;
  preferred_length: WritingLength;
  sentence_complexity: WritingComplexity;
  technical_detail: WritingTechnicalDetail;
  vocabulary: WritingVocabulary;
  phrases_to_avoid: string[];
  additional_instructions: string;
  created_at: string;
  updated_at: string;
}

export interface WritingSample {
  id: number;
  candidate_id: number;
  title: string;
  body: string;
  category: WritingSampleCategory;
  origin: WritingSampleOrigin;
  is_approved_style_reference: boolean;
  source_answer_id: number | null;
  created_at: string;
  updated_at: string;
}

export type PreparationState = 'preparing' | 'needs_review' | 'ready' | 'failed' | 'cancelled';
export type PreparationAnswerOrigin = 'reused' | 'adapted' | 'generated';
export type PreparationItemStatus = 'draft' | 'approved' | 'rejected' | 'needs_review';

export interface PreparationAnswer {
  id: number;
  question: string;
  answer_text: string;
  category: AnswerCategory;
  origin: PreparationAnswerOrigin;
  status: PreparationItemStatus;
  source_answer_id: number | null;
  is_sensitive: boolean;
  canonical_fact_ids: number[];
  unsupported_claims: unknown[];
  missing_information: unknown[];
  created_at: string;
  updated_at: string;
}

export interface ApplicationPreparation {
  id: number;
  candidate_id: number;
  job_id: number | null;
  source_resume_id: number | null;
  state: PreparationState;
  snapshot_job_title: string;
  snapshot_employer: string;
  snapshot_description: string;
  snapshot_apply_url: string;
  snapshot_content_hash: string;
  analysis: {
    summary?: string;
    required?: { text: string; evidence?: string }[];
    preferred?: { text: string; evidence?: string }[];
    technologies?: { text: string; evidence?: string }[];
    education?: { text: string; evidence?: string }[];
    experience?: { text: string; evidence?: string }[];
    work_authorization?: { text: string; evidence?: string }[];
    location?: { text: string; evidence?: string }[];
    employment_type?: { text: string; evidence?: string }[];
    responsibilities?: { text: string; evidence?: string }[];
  };
  match_report: {
    matched?: { text: string; group: string; evidence?: string }[];
    missing?: { text: string; reason?: string }[];
    uncertain?: { text: string; reason?: string }[];
  };
  tailored_resume: {
    header?: Record<string, string | null>;
    education?: { title: string; detail: unknown }[];
    work_experience?: { title: string; detail: unknown }[];
    projects?: { title: string; detail: unknown }[];
    skills?: { title: string; detail: unknown }[];
    achievements?: { title: string; detail: unknown }[];
  };
  tailored_resume_status: PreparationItemStatus;
  design_limitation: string;
  error_message: string;
  has_docx: boolean;
  has_pdf: boolean;
  answers: PreparationAnswer[];
  created_at: string;
  updated_at: string;
}

export interface AIStatus {
  enabled: boolean;
  provider: string;
  model: string;
  configured: boolean;
  available: boolean;
}
