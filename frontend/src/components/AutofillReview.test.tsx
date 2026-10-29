import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ApplicationPreparation, AutofillSession } from '../api/types'
import { AutofillReview } from './AutofillReview'
import { resetAutofillOpenings } from './autofillOpening'

vi.mock('../api/client', () => ({
  api: {
    openAutofillSession: vi.fn(),
    fillAutofillSession: vi.fn(),
    refreshAutofillSession: vi.fn(),
    regenerateAutofillDraft: vi.fn(),
    updatePreparationAnswer: vi.fn(),
    cancelAutofillSession: vi.fn(),
    submitAutofillSession: vi.fn(),
  },
}))

import { api } from '../api/client'

const prep = {
  id: 9,
  snapshot_job_title: 'Backend Intern',
  snapshot_employer: 'Northwind',
  snapshot_apply_url: 'https://boards.greenhouse.io/northwind/jobs/15',
} as ApplicationPreparation

const session: AutofillSession = {
  id: 'sess',
  state: 'ready_to_fill',
  preparation_id: 9,
  employer: 'Northwind',
  job_title: 'Backend Intern',
  apply_url: 'https://boards.greenhouse.io/northwind/jobs/15',
  message: 'Review the plan.',
  result: null,
  plan: {
    ready: [
      {
        field_id: 'email',
        label: 'Email',
        semantic: 'email',
        proposed_value: 'ada@example.com',
        proposed_replacement: null,
        existing_value: null,
        required: true,
        uncertainty: null,
        source_kind: 'profile',
      },
    ],
    clarification: [],
    missing_required: [{ field_id: 'phone', label: 'Phone', semantic: 'phone', proposed_value: null, proposed_replacement: null, existing_value: null, required: true, uncertainty: 'No verified value is available.', source_kind: null }],
    sensitive: [{ field_id: 'work', label: 'Work authorization', semantic: 'sensitive', proposed_value: null, proposed_replacement: null, existing_value: null, required: true, uncertainty: null, source_kind: null }],
    unsupported: [{ field_id: 'school', label: 'School', semantic: 'unknown', proposed_value: null, proposed_replacement: null, existing_value: null, required: false, uncertainty: null, source_kind: null }],
    preserve_existing: [],
    resume: {
      status: 'ready',
      kind: 'original',
      display_name: 'Backend SWE Resume',
      file_format: 'pdf',
      eligible_for_attach: true,
      review_required: false,
      reason: 'The approved original resume selected for this preparation will be used.',
    },
    answers: {
      matched: [
        {
          field_id: 'why',
          label: 'Why are you interested in this role?',
          required: false,
          proposed_text: 'I enjoy building small tools.',
          proposed_replacement: null,
          existing_value: null,
          source: 'job_specific',
          approval_status: 'approved',
          uncertainty: null,
          match_kind: 'exact_match',
          explanation: 'Approved answer reused because this application already has an approved answer for this question.',
          eligible_for_fill: true,
          review_required: false,
        },
      ],
      missing: [],
      ambiguous: [],
      sensitive: [],
      preserved: [],
    },
  },
}

describe('AutofillReview', () => {
  afterEach(() => {
    resetAutofillOpenings()
    cleanup()
  })

  it('shows the plan and can exclude a field before filling', async () => {
    vi.mocked(api.openAutofillSession).mockResolvedValue(session)
    vi.mocked(api.fillAutofillSession).mockResolvedValue({
      ...session,
      state: 'filled_for_review',
      result: {
        outcomes: [{ field_id: 'why', label: 'Why are you interested in this role?', status: 'filled', detail: 'Verified.' }],
        resume_status: 'attached',
        resume_detail: 'Attached Backend SWE Resume.',
        stopped: null,
        submitted: false,
        unresolved: ['Phone'],
      },
    })
    render(<AutofillReview prep={prep} />)
    fireEvent.click(screen.getByRole('button', { name: 'Apply with CareerPilot' }))
    expect(await screen.findByText('Backend Intern')).toBeInTheDocument()
    expect(screen.getByText(/Backend SWE Resume/)).toBeInTheDocument()
    expect(screen.getByText(/ada@example.com/)).toBeInTheDocument()
    expect(screen.getByText(/I enjoy building small tools/)).toBeInTheDocument()
    expect(screen.getByText(/Exact match/)).toBeInTheDocument()
    expect(screen.getByText(/Approved answer reused because this application already has an approved answer/)).toBeInTheDocument()
    expect(screen.getByText(/Autofill permitted/)).toBeInTheDocument()
    expect(screen.getByText(/Phone: No verified value is available/)).toBeInTheDocument()
    expect(screen.getByText(/Work authorization:/)).toBeInTheDocument()
    expect(screen.getByText(/School:/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /submit/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /Email/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Fill approved fields' }))
    expect(api.fillAutofillSession).toHaveBeenCalledWith('sess', {
      included_field_ids: ['why'],
      overwrite_field_ids: [],
      attach_resume: true,
    })
    expect(await screen.findByText(/Submitted by CareerPilot: no/)).toBeInTheDocument()
  })

  it('shows autofill for a Greenhouse job whose public link is the company site', () => {
    render(
      <AutofillReview
        prep={{
          ...prep,
          snapshot_apply_url: 'https://stripe.com/jobs/search?gh_jid=8128744',
          greenhouse_apply_url: 'https://boards.greenhouse.io/embed/job_app?for=stripe&token=8128744',
          greenhouse_autofill_note: '',
        }}
      />,
    )
    expect(screen.getByRole('button', { name: 'Apply with CareerPilot' })).toBeInTheDocument()
    expect(screen.getByText(/embed\/job_app/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /submit/i })).not.toBeInTheDocument()
  })

  it('shows a configuration message instead of hiding a Greenhouse job it cannot open', () => {
    render(
      <AutofillReview
        prep={{
          ...prep,
          snapshot_apply_url: 'https://example.com/jobs/1',
          greenhouse_apply_url: null,
          greenhouse_autofill_note: 'This Greenhouse job is missing a board token or job id, so the application form cannot be opened.',
        }}
      />,
    )
    expect(screen.getByText(/missing a board token/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Apply with CareerPilot' })).not.toBeInTheDocument()
  })

  it('lists a missing field and an unsupported field once and says when filling is permitted', async () => {
    vi.mocked(api.openAutofillSession).mockResolvedValue({
      ...session,
      plan: session.plan && {
        ...session.plan,
        blockers: [],
        missing_required: [
          session.plan.missing_required[0],
          { ...session.plan.missing_required[0], field_id: 'phone-2' },
        ],
        unsupported: [session.plan.unsupported[0], { ...session.plan.unsupported[0], field_id: 'school-2' }],
      },
    })
    render(<AutofillReview prep={prep} />)
    fireEvent.click(screen.getByRole('button', { name: 'Apply with CareerPilot' }))
    expect(await screen.findByText(/Filling is permitted/)).toBeInTheDocument()
    expect(screen.getAllByText(/Phone:/)).toHaveLength(1)
    expect(screen.getAllByText(/School:/)).toHaveLength(1)
  })

  it('shows readiness reasons and still has no submit control', async () => {
    vi.mocked(api.openAutofillSession).mockResolvedValue({
      ...session,
      readiness: {
        status: 'needs_review',
        checks: [
          { code: 'required_fields', status: 'needs_review', detail: 'Phone has not been filled yet.' },
          { code: 'job_identity', status: 'passed', detail: 'The open page matches.' },
        ],
      },
    })
    render(<AutofillReview prep={prep} />)
    fireEvent.click(screen.getByRole('button', { name: 'Apply with CareerPilot' }))
    expect(await screen.findByText(/Needs review before submission/)).toBeInTheDocument()
    expect(screen.getByText(/Phone has not been filled yet/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /submit/i })).not.toBeInTheDocument()
  })

  it('asks for confirmation before submitting this application only', async () => {
    vi.mocked(api.openAutofillSession).mockResolvedValue({
      ...session,
      state: 'filled_for_review',
      application_status: 'ready_to_submit',
      readiness: {
        status: 'ready_to_submit',
        checks: [
          { code: 'required_fields', status: 'passed', detail: 'Every required field was filled or already had a value.' },
          { code: 'sensitive_questions', status: 'passed', detail: 'No required sensitive questions are unanswered.' },
        ],
      },
    })
    vi.mocked(api.submitAutofillSession).mockResolvedValue({
      ...session,
      state: 'submitted',
      application_status: 'submitted',
      message: 'The employer page confirmed the application was received.',
    })
    render(<AutofillReview prep={prep} />)
    fireEvent.click(screen.getByRole('button', { name: 'Apply with CareerPilot' }))
    expect(await screen.findByText(/sends it to Northwind/)).toBeInTheDocument()
    expect(screen.getAllByText(/Backend SWE Resume/).length).toBeGreaterThan(0)
    const submit = screen.getByRole('button', { name: 'Submit this application' })
    expect(submit).toBeDisabled()
    fireEvent.click(submit)
    expect(api.submitAutofillSession).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('checkbox', { name: /I confirm this submission for Backend Intern at Northwind only/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit this application' }))
    expect(api.submitAutofillSession).toHaveBeenCalledWith('sess', {
      confirm: true,
      preparation_id: 9,
      apply_url: 'https://boards.greenhouse.io/northwind/jobs/15',
    })
    expect(await screen.findByText(/Successfully submitted/)).toBeInTheDocument()
  })

  it('opens one browser when two reviews start together and does not submit', async () => {
    vi.mocked(api.openAutofillSession).mockResolvedValue({
      ...session,
      readiness: { status: 'needs_review', checks: [{ code: 'required_fields', status: 'needs_review', detail: 'Phone has not been filled yet.' }] },
    })
    vi.mocked(api.fillAutofillSession).mockResolvedValue({
      ...session,
      state: 'filled_for_review',
      application_status: 'needs_review',
      message: 'The browser is open for review. CareerPilot did not submit the application.',
      readiness: { status: 'needs_review', checks: [{ code: 'required_fields', status: 'needs_review', detail: 'Phone has not been filled yet.' }] },
      result: { outcomes: [], resume_status: 'skipped', resume_detail: '', stopped: null, submitted: false, unresolved: ['Phone'] },
    })
    render(
      <>
        <AutofillReview prep={prep} autoStart hideLauncher />
        <AutofillReview prep={prep} autoStart hideLauncher />
      </>,
    )
    expect(await screen.findAllByText(/Needs review before submission/)).toHaveLength(2)
    expect(api.openAutofillSession).toHaveBeenCalledTimes(1)
    expect(api.fillAutofillSession).toHaveBeenCalledTimes(1)
    expect(api.submitAutofillSession).not.toHaveBeenCalled()
    expect(api.cancelAutofillSession).not.toHaveBeenCalled()
  })

  it('shows a navigation failure and can still stop a session that stayed open', async () => {
    vi.mocked(api.openAutofillSession).mockResolvedValue({
      ...session,
      state: 'failed',
      message: 'The browser left the Greenhouse application page.',
    })
    render(<AutofillReview prep={prep} autoStart hideLauncher />)
    expect((await screen.findAllByText(/The browser left the Greenhouse application page/)).length).toBeGreaterThan(0)
    expect(api.fillAutofillSession).not.toHaveBeenCalled()
    expect(api.submitAutofillSession).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument()
    vi.mocked(api.openAutofillSession).mockResolvedValue(session)
    fireEvent.click(screen.getByRole('button', { name: 'Try the form again' }))
    expect(await screen.findByText(/ready to fill/)).toBeInTheDocument()
    vi.mocked(api.cancelAutofillSession).mockResolvedValue({ ...session, state: 'cancelled', message: 'The browser session was stopped.' })
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }))
    expect(await screen.findByText(/The browser session was stopped/)).toBeInTheDocument()
    expect(api.cancelAutofillSession).toHaveBeenCalledWith('sess')
  })

  it('reviews a draft and fills only that answer after approval', async () => {
    const drafted: AutofillSession = {
      ...session,
      plan: {
        ...session.plan!,
        answers: {
          ...session.plan!.answers,
          missing: [
            {
              field_id: 'project',
              label: 'Describe a technical project you built.',
              required: false,
              proposed_text: 'I built the Lantern API.',
              proposed_replacement: null,
              existing_value: null,
              source: 'job_specific',
              source_id: 44,
              approval_status: 'draft',
              uncertainty: 'This draft is not filled until you approve it.',
              match_kind: 'no_match',
              explanation: 'Draft only. Supported by verified facts: project: Lantern.',
              supporting_facts: ['project: Lantern'],
              eligible_for_fill: false,
              review_required: true,
            },
          ],
        },
      },
    }
    vi.mocked(api.openAutofillSession).mockResolvedValue(drafted)
    vi.mocked(api.updatePreparationAnswer).mockResolvedValue(prep)
    vi.mocked(api.refreshAutofillSession).mockResolvedValue(drafted)
    vi.mocked(api.fillAutofillSession).mockResolvedValue({
      ...drafted,
      state: 'filled_for_review',
      readiness: {
        status: 'needs_review',
        checks: [{ code: 'required_fields', status: 'needs_review', detail: 'Phone is still unanswered.' }],
      },
    })
    render(<AutofillReview prep={prep} />)
    fireEvent.click(screen.getByRole('button', { name: 'Apply with CareerPilot' }))
    expect(await screen.findByText('Draft answers')).toBeInTheDocument()
    expect(screen.getAllByText(/project: Lantern/).length).toBeGreaterThan(0)
    expect(screen.getByText(/not filled until you approve it/)).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: /Describe a technical project/ })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Draft for Describe a technical project you built.'), {
      target: { value: 'I built the Lantern API for merchants.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Approve Describe a technical project you built.' }))
    await waitFor(() => {
      expect(api.fillAutofillSession).toHaveBeenCalledWith('sess', {
        included_field_ids: ['project'],
        overwrite_field_ids: [],
        attach_resume: false,
      })
    })
    expect(api.updatePreparationAnswer).toHaveBeenCalledWith(9, 44, {
      answer_text: 'I built the Lantern API for merchants.',
      status: 'approved',
    })
    expect(api.refreshAutofillSession).toHaveBeenCalledWith('sess')
    expect(api.submitAutofillSession).not.toHaveBeenCalled()
    expect(await screen.findByText(/Phone is still unanswered/)).toBeInTheDocument()
  })

  it('stays hidden for a non-Greenhouse preparation', () => {
    const { container } = render(
      <AutofillReview
        prep={{
          ...prep,
          snapshot_apply_url: 'https://jobs.lever.co/northwind/abc',
          greenhouse_apply_url: null,
          greenhouse_autofill_note: '',
        }}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
