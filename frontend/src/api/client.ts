import type {
  Candidate,
  CandidateFact,
  CandidateFactUpdateInput,
  CandidateInput,
  DiscoveryRun,
  Job,
  JobSource,
  JobSourceInput,
  JobState,
  ListCandidateFactsParams,
  ListJobsParams,
  ListJobsResult,
  Preferences,
  Resume,
  ResumeUploadResult,
  SchedulerStatus,
} from './types';

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000';

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(`API error ${status}: ${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
  } catch (err) {
    throw new ApiError(0, `Could not reach the CareerPilot API at ${BASE_URL}. Is the backend running? (${String(err)})`);
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      // response had no JSON body; fall back to statusText
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string; database: string }>('/health'),

  getCandidate: () => request<Candidate | null>('/api/candidate'),
  createCandidate: (data: Partial<CandidateInput>) =>
    request<Candidate>('/api/candidate', { method: 'POST', body: JSON.stringify(data) }),
  updateCandidate: (data: Partial<CandidateInput>) =>
    request<Candidate>('/api/candidate', { method: 'PATCH', body: JSON.stringify(data) }),

  getPreferences: () => request<Preferences>('/api/candidate/preferences'),
  updatePreferences: (data: Preferences) =>
    request<Preferences>('/api/candidate/preferences', { method: 'PUT', body: JSON.stringify(data) }),

  listJobSources: () => request<JobSource[]>('/api/job-sources'),
  createJobSource: (data: JobSourceInput) =>
    request<JobSource>('/api/job-sources', { method: 'POST', body: JSON.stringify(data) }),
  updateJobSource: (id: number, data: Partial<Pick<JobSource, 'is_enabled' | 'fetch_interval_minutes'>>) =>
    request<JobSource>(`/api/job-sources/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),

  listJobs: async (params?: ListJobsParams): Promise<ListJobsResult> => {
    const query = new URLSearchParams();
    if (params?.view) query.set('view', params.view);
    (params?.states ?? []).forEach((s) => query.append('states', s));
    if (params?.include_inactive) query.set('include_inactive', 'true');
    if (params?.min_score != null) query.set('min_score', String(params.min_score));
    (params?.role_categories ?? []).forEach((v) => query.append('role_categories', v));
    (params?.employment_types ?? []).forEach((v) => query.append('employment_types', v));
    (params?.remote_types ?? []).forEach((v) => query.append('remote_types', v));
    (params?.eligibility ?? []).forEach((v) => query.append('eligibility', v));
    (params?.relevance ?? []).forEach((v) => query.append('relevance', v));
    (params?.companies ?? []).forEach((v) => query.append('companies', v));
    if (params?.location) query.set('location', params.location);
    if (params?.posted_within_days != null) query.set('posted_within_days', String(params.posted_within_days));
    if (params?.sort) query.set('sort', params.sort);
    query.set('limit', String(params?.limit ?? 50));
    query.set('offset', String(params?.offset ?? 0));

    let response: Response;
    try {
      response = await fetch(`${BASE_URL}/api/jobs?${query.toString()}`, {
        headers: { 'Content-Type': 'application/json' },
      });
    } catch (err) {
      throw new ApiError(0, `Could not reach the CareerPilot API at ${BASE_URL}. Is the backend running? (${String(err)})`);
    }
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = await response.json();
        detail = body.detail ?? JSON.stringify(body);
      } catch {
        // no JSON body
      }
      throw new ApiError(response.status, detail);
    }
    const jobs = (await response.json()) as Job[];
    const total = Number(response.headers.get('X-Total-Count') ?? jobs.length);
    return { jobs, total };
  },
  setJobState: (jobId: number, state: JobState, stateReason?: string) =>
    request<Job>(`/api/jobs/${jobId}/state`, {
      method: 'PATCH',
      body: JSON.stringify({ state, state_reason: stateReason ?? null }),
    }),

  triggerDiscoveryRun: () => request<DiscoveryRun>('/api/discovery/runs', { method: 'POST' }),
  listDiscoveryRuns: (limit = 10) => request<DiscoveryRun[]>(`/api/discovery/runs?limit=${limit}`),
  getLatestDiscoveryRun: () => request<DiscoveryRun | null>('/api/discovery/runs/latest'),
  getSchedulerStatus: () => request<SchedulerStatus>('/api/discovery/scheduler-status'),

  // --- Phase 2.1: resume upload, parsing, verified fact review ---
  // Uses `fetch` directly (not the generic `request` helper) because a
  // multipart/form-data body must NOT get the `Content-Type: application/json`
  // header `request` always sets -- the browser sets the correct multipart
  // boundary itself when given a FormData body.
  uploadResume: async (file: File): Promise<ResumeUploadResult> => {
    const formData = new FormData();
    formData.append('file', file);

    let response: Response;
    try {
      response = await fetch(`${BASE_URL}/api/resumes`, { method: 'POST', body: formData });
    } catch (err) {
      throw new ApiError(0, `Could not reach the CareerPilot API at ${BASE_URL}. Is the backend running? (${String(err)})`);
    }
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = await response.json();
        detail = body.detail ?? JSON.stringify(body);
      } catch {
        // no JSON body
      }
      throw new ApiError(response.status, detail);
    }
    return (await response.json()) as ResumeUploadResult;
  },
  listResumes: () => request<Resume[]>('/api/resumes'),
  listResumeFacts: (resumeId: number) => request<CandidateFact[]>(`/api/resumes/${resumeId}/facts`),
  listCandidateFacts: (params?: ListCandidateFactsParams) => {
    const query = new URLSearchParams();
    if (params?.fact_type) query.set('fact_type', params.fact_type);
    if (params?.verification_status) query.set('verification_status', params.verification_status);
    const qs = query.toString();
    return request<CandidateFact[]>(`/api/candidate/facts${qs ? `?${qs}` : ''}`);
  },
  updateCandidateFact: (factId: number, data: CandidateFactUpdateInput) =>
    request<CandidateFact>(`/api/candidate/facts/${factId}`, { method: 'PATCH', body: JSON.stringify(data) }),
};
