import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Job } from '../api/types'
import { ApplicationWorkflow } from './ApplicationWorkflow'
import { resetAutofillOpenings } from './autofillOpening'

vi.mock('virtual:careerpilot-token', () => ({ default: 'test-token' }))

vi.mock('../api/client', () => ({
  api: {
    startApplicationWorkflow: vi.fn(),
    getApplication: vi.fn(),
    resolveApplication: vi.fn(),
    openAutofillSession: vi.fn(),
    fillAutofillSession: vi.fn(),
    attemptAutoApply: vi.fn(),
    submitAutofillSession: vi.fn(),
    cancelAutofillSession: vi.fn(),
  },
}))

import { api } from '../api/client'

const job = {
  id: 15,
  title: 'Backend Intern',
  employer_name: 'Northwind',
  provider: 'greenhouse',
  assessment: { eligibility: 'unknown' },
} as Job

const preparation = {
  id: 9,
  snapshot_job_title: 'Backend Intern',
  snapshot_employer: 'Northwind',
  snapshot_apply_url: 'https://boards.greenhouse.io/northwind/jobs/15',
  greenhouse_apply_url: 'https://boards.greenhouse.io/northwind/jobs/15',
  greenhouse_autofill_note: '',
  selected_resume_name: null,
  resume_selection_reason: 'No approved resume profiles are available.',
  application_id: 4,
  application_status: 'preparing',
  answers: [],
  analysis: { summary: '' },
  match_report: {},
  tailored_resume: {},
}

describe('ApplicationWorkflow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetAutofillOpenings()
  })
  afterEach(() => cleanup())

  it('prepares and fills approved fields without submitting', async () => {
    vi.mocked(api.startApplicationWorkflow).mockResolvedValue({
      reused: false,
      can_open_browser: true,
      eligibility: 'unknown',
      eligibility_detail: 'Eligibility is unknown, so CareerPilot will not submit until it can be verified.',
      message: 'Nothing is sent until you confirm this employer and job.',
      preparation: preparation as never,
    })
    vi.mocked(api.getApplication).mockResolvedValue({
      id: 4,
      status: 'preparing',
      submitted_at: null,
      confirmation: null,
      failure_reason: null,
      resubmit_after: null,
      events: [],
    } as never)
    vi.mocked(api.openAutofillSession).mockResolvedValue({
      id: 'sess',
      state: 'ready_to_fill',
      preparation_id: 9,
      employer: 'Northwind',
      job_title: 'Backend Intern',
      apply_url: 'https://boards.greenhouse.io/northwind/jobs/15',
      message: 'Review the plan.',
      application_status: 'needs_review',
      readiness: {
        status: 'needs_review',
        checks: [{ code: 'graduation', status: 'needs_review', detail: 'Eligibility is unknown.' }],
      },
      plan: {
        ready: [{ field_id: 'email', label: 'Email' }],
        clarification: [],
        missing_required: [{ field_id: 'phone', label: 'Phone' }],
        sensitive: [{ field_id: 'work', label: 'Work authorization' }],
        unsupported: [],
        preserve_existing: [],
        resume: { display_name: '', kind: 'original', eligible_for_attach: false, reason: 'No approved resume.', status: 'missing', file_format: null, review_required: true },
        answers: { matched: [], missing: [], ambiguous: [], sensitive: [{ field_id: 'q', label: 'Work authorization', approval_status: 'needs_review' }], preserved: [] },
      },
      result: null,
    } as never)
    vi.mocked(api.fillAutofillSession).mockResolvedValue({
      id: 'sess',
      state: 'filled_for_review',
      preparation_id: 9,
      employer: 'Northwind',
      job_title: 'Backend Intern',
      apply_url: 'https://boards.greenhouse.io/northwind/jobs/15',
      message: 'The browser is open for review. CareerPilot did not submit the application.',
      application_status: 'needs_review',
      readiness: {
        status: 'needs_review',
        checks: [{ code: 'resume', status: 'needs_review', detail: 'No approved resume is available.' }],
      },
      plan: {
        ready: [],
        clarification: [],
        missing_required: [],
        sensitive: [],
        unsupported: [],
        preserve_existing: [],
        resume: { display_name: '', kind: 'original', eligible_for_attach: false, reason: 'No approved resume.', status: 'missing', file_format: null, review_required: true },
        answers: { matched: [], missing: [], ambiguous: [], sensitive: [], preserved: [] },
      },
      result: { outcomes: [{ field_id: 'email', label: 'Email', status: 'filled', detail: '' }], resume_status: 'skipped', resume_detail: 'No approved resume.', stopped: null, submitted: false, unresolved: ['Phone'] },
      completion: { total: 4, autofilled: 1, already_completed: 0, manual: 3, required_unanswered: 1, percent: 25 },
    } as never)
    render(<ApplicationWorkflow job={job} onStarted={() => undefined} />)
    fireEvent.click(screen.getByRole('button', { name: 'Apply with CareerPilot' }))
    expect(await screen.findByText(/Eligibility: unknown/)).toBeInTheDocument()
    expect(screen.getAllByText(/No approved resume/).length).toBeGreaterThan(0)
    expect(await screen.findByText(/Needs review before submission/)).toBeInTheDocument()
    expect(screen.getByText('1 of 4 fields completed.')).toBeInTheDocument()
    expect(screen.getByText(/Eligibility: unknown/)).toBeInTheDocument()
    expect(api.fillAutofillSession).toHaveBeenCalledWith('sess', {
      included_field_ids: ['email'],
      overwrite_field_ids: [],
      attach_resume: false,
    })
    expect(api.submitAutofillSession).not.toHaveBeenCalled()
    expect(api.attemptAutoApply).not.toHaveBeenCalled()
    expect(screen.getByText('Workflow mode: Review.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Submit this application' })).not.toBeInTheDocument()
  })

  it('submits from one click only when Auto-Apply returns a result', async () => {
    vi.mocked(api.startApplicationWorkflow).mockResolvedValue({
      reused: false,
      can_open_browser: true,
      eligibility: 'eligible',
      eligibility_detail: 'Eligible.',
      mode: 'auto_apply',
      message: 'Auto-Apply will check this form after approved fields are filled.',
      preparation: preparation as never,
    })
    vi.mocked(api.getApplication).mockResolvedValue({
      id: 4,
      status: 'preparing',
      submitted_at: null,
      confirmation: null,
      failure_reason: null,
      resubmit_after: null,
      events: [],
    } as never)
    vi.mocked(api.openAutofillSession).mockResolvedValue({
      id: 'sess',
      state: 'ready_to_fill',
      preparation_id: 9,
      employer: 'Northwind',
      job_title: 'Backend Intern',
      apply_url: 'https://boards.greenhouse.io/northwind/jobs/15',
      message: 'Review the plan.',
      plan: { ready: [], answers: { matched: [] }, resume: { eligible_for_attach: false } },
    } as never)
    vi.mocked(api.fillAutofillSession).mockResolvedValue({
      id: 'sess',
      state: 'filled_for_review',
      preparation_id: 9,
      employer: 'Northwind',
      job_title: 'Backend Intern',
      apply_url: 'https://boards.greenhouse.io/northwind/jobs/15',
      message: 'Filled.',
      readiness: { status: 'ready_to_submit', checks: [] },
      plan: { ready: [], answers: { matched: [] }, resume: { eligible_for_attach: false, display_name: '', kind: 'original', reason: '', status: 'missing', file_format: null, review_required: false } },
    } as never)
    vi.mocked(api.attemptAutoApply).mockResolvedValue({
      id: 'sess',
      state: 'needs_review',
      phase: 'needs_review',
      mode: 'auto_apply',
      preparation_id: 9,
      employer: 'Northwind',
      job_title: 'Backend Intern',
      apply_url: 'https://boards.greenhouse.io/northwind/jobs/15',
      message: 'The job category is outside the authorized categories.',
      auto_apply_reasons: ['The job category is outside the authorized categories.'],
      application_status: 'needs_review',
      readiness: { status: 'needs_review', checks: [] },
      plan: null,
      result: null,
    } as never)
    render(<ApplicationWorkflow job={job} onStarted={() => undefined} />)
    fireEvent.click(screen.getByRole('button', { name: 'Apply with CareerPilot' }))
    expect(await screen.findByText('Workflow mode: Auto-Apply.')).toBeInTheDocument()
    expect(await screen.findByText('The job category is outside the authorized categories.')).toBeInTheDocument()
    expect(screen.getByText('Workflow: Needs review')).toBeInTheDocument()
    expect(api.attemptAutoApply).toHaveBeenCalledWith('sess')
    expect(api.submitAutofillSession).not.toHaveBeenCalled()
    expect(screen.getByText(/Auto-Apply paused/)).toBeInTheDocument()
  })

  it('shows an unsupported board without opening a browser', async () => {
    vi.mocked(api.startApplicationWorkflow).mockRejectedValue(new Error('API error 409: Lever applications are not supported yet. CareerPilot did not open a browser or submit.'))
    render(<ApplicationWorkflow job={{ ...job, provider: 'lever' }} onStarted={() => undefined} />)
    const button = screen.getByRole('button', { name: 'Apply with CareerPilot' })
    fireEvent.click(button)
    fireEvent.click(button)
    expect(await screen.findByText(/Lever applications are not supported yet/)).toBeInTheDocument()
    expect(api.startApplicationWorkflow).toHaveBeenCalledTimes(1)
    expect(api.openAutofillSession).not.toHaveBeenCalled()
    expect(api.submitAutofillSession).not.toHaveBeenCalled()
  })
})