import type {
  Candidate,
  CandidateInput,
  DiscoveryRun,
  Job,
  JobSource,
  JobSourceInput,
  JobState,
  Preferences,
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

  listJobs: (params?: { state?: JobState; include_inactive?: boolean }) => {
    const query = new URLSearchParams();
    if (params?.state) query.set('state', params.state);
    if (params?.include_inactive) query.set('include_inactive', 'true');
    const qs = query.toString();
    return request<Job[]>(`/api/jobs${qs ? `?${qs}` : ''}`);
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
};
