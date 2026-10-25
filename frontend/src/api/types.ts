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
