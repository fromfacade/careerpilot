import type {
  Candidate,
  CandidateFact,
  CandidateFactBulkUpdateInput,
  CandidateFactUpdateInput,
  ResumeDeleteInput,
  ResumeDeleteResult,
  ResumeReprocessResult,
  CandidateInput,
  DiscoveryRun,
  FactType,
  FactValue,
  FactVerificationStatus,
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

import localToken from 'virtual:careerpilot-token';

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
      headers: {
        'Content-Type': 'application/json',
        ...(path.startsWith('/api/autofill/sessions') ? { 'X-CareerPilot-Token': localToken } : {}),
        ...(init?.headers ?? {}),
      },
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
  bulkUpdateCandidateFacts: (data: CandidateFactBulkUpdateInput) =>
    request<CandidateFact[]>('/api/candidate/facts/bulk', { method: 'POST', body: JSON.stringify(data) }),
  reprocessResume: (resumeId: number) =>
    request<ResumeReprocessResult>(`/api/resumes/${resumeId}/reprocess`, { method: 'POST' }),
  setPrimaryResume: (resumeId: number) =>
    request<Resume>(`/api/resumes/${resumeId}/primary`, { method: 'POST' }),
  updateResumeProfile: (resumeId: number, data: Record<string, unknown>) =>
    request<Resume>(`/api/resumes/${resumeId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  downloadResumeFile: async (resumeId: number, filename: string) => {
    const response = await fetch(`${BASE_URL}/api/resumes/${resumeId}/file`);
    if (!response.ok) throw new ApiError(response.status, 'Could not download the original resume.');
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  },
  deleteResume: (resumeId: number, data: ResumeDeleteInput = {}) =>
    request<ResumeDeleteResult>(`/api/resumes/${resumeId}`, {
      method: 'DELETE',
      body: JSON.stringify({
        delete_verified_facts: data.delete_verified_facts ?? false,
        replacement_resume_id: data.replacement_resume_id ?? null,
      }),
    }),

  getAIStatus: () => request<import('./types').AIStatus>('/api/ai/status'),
  listCanonicalFacts: (params?: {
    fact_type?: FactType;
    status?: import('./types').CanonicalFactStatus;
    verification_status?: FactVerificationStatus;
  }) => {
    const query = new URLSearchParams();
    if (params?.fact_type) query.set('fact_type', params.fact_type);
    if (params?.status) query.set('status', params.status);
    if (params?.verification_status) query.set('verification_status', params.verification_status);
    const qs = query.toString();
    return request<import('./types').CanonicalFact[]>(`/api/candidate/canonical-facts${qs ? `?${qs}` : ''}`);
  },
  createCanonicalFact: (data: { fact_type: FactType; fact_key: string; fact_value: FactValue }) =>
    request<import('./types').CanonicalFact>('/api/candidate/canonical-facts', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  importCanonicalFacts: (factIds?: number[]) =>
    request<import('./types').CanonicalFactImportResult>('/api/candidate/canonical-facts/import', {
      method: 'POST',
      body: JSON.stringify({ fact_ids: factIds ?? null }),
    }),
  updateCanonicalFact: (
    factId: number,
    data: { fact_key?: string; fact_value?: FactValue; verification_status?: Exclude<FactVerificationStatus, 'unverified'> },
  ) =>
    request<import('./types').CanonicalFact>(`/api/candidate/canonical-facts/${factId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  archiveCanonicalFact: (factId: number) =>
    request<import('./types').CanonicalFact>(`/api/candidate/canonical-facts/${factId}/archive`, { method: 'POST' }),
  resolveCanonicalConflict: (factId: number, keep: 'existing' | 'incoming') =>
    request<import('./types').CanonicalFact>(`/api/candidate/canonical-facts/${factId}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ keep }),
    }),
  deleteCanonicalFact: (factId: number) =>
    request<void>(`/api/candidate/canonical-facts/${factId}`, { method: 'DELETE' }),
  listAnswers: (params?: { category?: string; status?: string; search?: string }) => {
    const query = new URLSearchParams();
    if (params?.category) query.set('category', params.category);
    if (params?.status) query.set('status', params.status);
    if (params?.search) query.set('search', params.search);
    const qs = query.toString();
    return request<import('./types').ApplicationAnswer[]>(`/api/candidate/answers${qs ? `?${qs}` : ''}`);
  },
  createAnswer: (data: Record<string, unknown>) =>
    request<import('./types').ApplicationAnswer>('/api/candidate/answers', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateAnswer: (answerId: number, data: Record<string, unknown>) =>
    request<import('./types').ApplicationAnswer>(`/api/candidate/answers/${answerId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  generateAnswer: (data: { question: string; category: string; job_id?: number }) =>
    request<import('./types').ApplicationAnswer>('/api/candidate/answers/generate', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteAnswer: (answerId: number) => request<void>(`/api/candidate/answers/${answerId}`, { method: 'DELETE' }),
  getAnswer: (answerId: number) => request<import('./types').ApplicationAnswer>(`/api/candidate/answers/${answerId}`),
  rewriteAnswer: (answerId: number) =>
    request<import('./types').ApplicationAnswer>(`/api/candidate/answers/${answerId}/rewrite`, { method: 'POST' }),
  getWritingStyle: () => request<import('./types').WritingStyleProfile>('/api/candidate/writing-style'),
  updateWritingStyle: (data: Partial<import('./types').WritingStyleProfile>) =>
    request<import('./types').WritingStyleProfile>('/api/candidate/writing-style', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  listWritingSamples: (params?: { category?: string; approved_only?: boolean }) => {
    const query = new URLSearchParams();
    if (params?.category) query.set('category', params.category);
    if (params?.approved_only) query.set('approved_only', 'true');
    const qs = query.toString();
    return request<import('./types').WritingSample[]>(`/api/candidate/writing-samples${qs ? `?${qs}` : ''}`);
  },
  createWritingSample: (data: Record<string, unknown>) =>
    request<import('./types').WritingSample>('/api/candidate/writing-samples', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateWritingSample: (sampleId: number, data: Record<string, unknown>) =>
    request<import('./types').WritingSample>(`/api/candidate/writing-samples/${sampleId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deleteWritingSample: (sampleId: number) =>
    request<void>(`/api/candidate/writing-samples/${sampleId}`, { method: 'DELETE' }),
  listApplications: () => request<import('./types').TrackedApplication[]>('/api/applications'),
  getApplication: (id: number) => request<import('./types').TrackedApplication>(`/api/applications/${id}`),
  resolveApplication: (id: number, data: { confirm: boolean; received: boolean; note: string }) =>
    request<import('./types').TrackedApplication>(`/api/applications/${id}/resolution`, {
      method: 'POST',
      headers: { 'X-CareerPilot-Token': localToken },
      body: JSON.stringify(data),
    }),
  listPreparations: () =>
    request<import('./types').ApplicationPreparation[]>('/api/preparations'),
  createPreparation: (jobId: number) =>
    request<import('./types').ApplicationPreparation>('/api/preparations', {
      method: 'POST',
      body: JSON.stringify({ job_id: jobId }),
    }),
  startApplicationWorkflow: (jobId: number) =>
    request<import('./types').ApplicationWorkflow>('/api/preparations/workflow', {
      method: 'POST',
      body: JSON.stringify({ job_id: jobId }),
    }),
  getPreparation: (id: number) =>
    request<import('./types').ApplicationPreparation>(`/api/preparations/${id}`),
  cancelPreparation: (id: number) =>
    request<import('./types').ApplicationPreparation>(`/api/preparations/${id}/cancel`, { method: 'POST' }),
  regeneratePreparation: (id: number) =>
    request<import('./types').ApplicationPreparation>(`/api/preparations/${id}/regenerate`, { method: 'POST' }),
  updatePreparationResume: (id: number, data: Record<string, unknown>) =>
    request<import('./types').ApplicationPreparation>(`/api/preparations/${id}/resume`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  selectPreparationResume: (id: number, resumeId: number) =>
    request<import('./types').ApplicationPreparation>(`/api/preparations/${id}/select-resume`, {
      method: 'POST',
      body: JSON.stringify({ resume_id: resumeId }),
    }),
  tailorPreparation: (id: number) =>
    request<import('./types').ApplicationPreparation>(`/api/preparations/${id}/tailor`, { method: 'POST' }),
  revertPreparationTailoring: (id: number) =>
    request<import('./types').ApplicationPreparation>(`/api/preparations/${id}/tailor/revert`, { method: 'POST' }),
  updatePreparationAnswer: (id: number, answerId: number, data: Record<string, unknown>) =>
    request<import('./types').ApplicationPreparation>(`/api/preparations/${id}/answers/${answerId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  preparationPdfPreviewUrl: (id: number) => `${BASE_URL}/api/preparations/${id}/documents/pdf?inline=1`,
  openAutofillSession: (preparationId: number) =>
    request<import('./types').AutofillSession>('/api/autofill/sessions', {
      method: 'POST',
      body: JSON.stringify({ preparation_id: preparationId }),
    }),
  fillAutofillSession: (
    sessionId: string,
    body: { included_field_ids: string[]; overwrite_field_ids: string[]; attach_resume: boolean },
  ) =>
    request<import('./types').AutofillSession>(`/api/autofill/sessions/${sessionId}/fill`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  cancelAutofillSession: (sessionId: string) =>
    request<import('./types').AutofillSession>(`/api/autofill/sessions/${sessionId}/cancel`, { method: 'POST' }),
  submitAutofillSession: (
    sessionId: string,
    body: { confirm: boolean; preparation_id: number; apply_url: string },
  ) =>
    request<import('./types').AutofillSession>(`/api/autofill/sessions/${sessionId}/submit`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  downloadPreparationDocument: async (id: number, kind: 'docx' | 'pdf' | 'original' | 'selected') => {
    const response = await fetch(`${BASE_URL}/api/preparations/${id}/documents/${kind}`);
    if (!response.ok) throw new ApiError(response.status, 'Could not download the prepared document.');
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = kind === 'original' || kind === 'selected' ? 'selected-resume' : `tailored-resume.${kind}`;
    link.click();
    URL.revokeObjectURL(url);
  },
};
