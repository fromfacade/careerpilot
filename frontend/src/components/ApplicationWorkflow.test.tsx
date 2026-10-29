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
    } as never)
    render(<ApplicationWorkflow job={job} onStarted={() => undefined} />)
    fireEvent.click(screen.getByRole('button', { name: 'Apply with CareerPilot' }))
    expect(await screen.findByText(/Eligibility: unknown/)).toBeInTheDocument()
    expect(screen.getAllByText(/No approved resume/).length).toBeGreaterThan(0)
    expect(await screen.findByText(/Needs review before submission/)).toBeInTheDocument()
    expect(api.fillAutofillSession).toHaveBeenCalledWith('sess', {
      included_field_ids: ['email'],
      overwrite_field_ids: [],
      attach_resume: false,
    })
    expect(api.submitAutofillSession).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: 'Submit this application' })).not.toBeInTheDocument()
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