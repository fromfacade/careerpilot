import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ApplicationPreparation } from '../api/types'
import { ApplicationPreparationPanel } from './ApplicationPreparationPanel'

vi.mock('virtual:careerpilot-token', () => ({ default: 'test-token' }))

vi.mock('../api/client', () => ({
  api: {
    listPreparations: vi.fn(),
    listResumes: vi.fn(),
    getApplication: vi.fn(),
    resolveApplication: vi.fn(),
    openAutofillSession: vi.fn(),
    fillAutofillSession: vi.fn(),
    cancelAutofillSession: vi.fn(),
  },
}))

import { api } from '../api/client'

const stripePrep = {
  id: 3,
  snapshot_job_title: 'Software Engineer, New Grad',
  snapshot_employer: 'Stripe',
  snapshot_apply_url: 'https://stripe.com/jobs/search?gh_jid=8128744',
  greenhouse_apply_url: 'https://boards.greenhouse.io/embed/job_app?for=stripe&token=8128744',
  greenhouse_autofill_note: '',
  snapshot_description: 'Build payments software.',
  state: 'needs_review',
  source_resume_id: null,
  selected_resume_name: 'Backend SWE Resume',
  resume_selection_reason: 'Approved original resume.',
  has_tailored_resume: false,
  tailored_resume_status: 'draft',
  tailored_resume: {},
  has_docx: false,
  has_pdf: false,
  error_message: '',
  design_limitation: '',
  analysis: { summary: 'Internship on the payments team.', required: [], preferred: [] },
  match_report: { matched: [], missing: [], uncertain: [] },
  answers: [],
  application_status: 'needs_review',
} as unknown as ApplicationPreparation

describe('ApplicationPreparationPanel autofill', () => {
  afterEach(() => cleanup())

  it('renders Greenhouse autofill controls for an existing company-site preparation', async () => {
    vi.mocked(api.listPreparations).mockResolvedValue([stripePrep])
    vi.mocked(api.listResumes).mockResolvedValue([])
    render(<ApplicationPreparationPanel selectedId={3} onSelected={() => undefined} />)
    expect(await screen.findByRole('button', { name: 'Apply with CareerPilot' })).toBeInTheDocument()
    expect(screen.getAllByText('Greenhouse autofill').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Application status: Needs review/).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: /submit/i })).not.toBeInTheDocument()
  })

  it('records a correction only after the user confirms the evidence', async () => {
    vi.mocked(api.listPreparations).mockResolvedValue([{ ...stripePrep, application_id: 9, application_status: 'confirmation_unknown' }])
    vi.mocked(api.listResumes).mockResolvedValue([])
    vi.mocked(api.getApplication).mockResolvedValue({
      id: 9,
      status: 'confirmation_unknown',
      submitted_at: null,
      confirmation: 'The page did not show a receipt.',
      failure_reason: 'The page did not show a receipt.',
      resubmit_after: null,
      events: [
        {
          id: 1,
          application_id: 9,
          previous_status: 'submitting',
          new_status: 'confirmation_unknown',
          reason: 'The page did not show a receipt.',
          source: 'browser',
          created_at: '2026-10-27T20:00:00Z',
        },
      ],
    } as never)
    vi.mocked(api.resolveApplication).mockResolvedValue({ id: 9, status: 'submitted', events: [] } as never)
    render(<ApplicationPreparationPanel selectedId={3} onSelected={() => undefined} />)
    expect(await screen.findByText(/Status history/)).toBeInTheDocument()
    expect(screen.getByText(/cannot verify whether the employer received/)).toBeInTheDocument()
    expect(screen.getByText(/Browser/)).toBeInTheDocument()
    const received = screen.getByRole('button', { name: 'Confirmed received' })
    expect(received).toBeDisabled()
    fireEvent.click(received)
    expect(api.resolveApplication).not.toHaveBeenCalled()
    fireEvent.change(screen.getByRole('textbox', { name: /What did you see/ }), { target: { value: 'The employer page said the application was received.' } })
    fireEvent.click(screen.getByRole('checkbox', { name: /I confirm this correction for Software Engineer, New Grad at Stripe only/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmed received' }))
    expect(api.resolveApplication).toHaveBeenCalledWith(9, {
      confirm: true,
      received: true,
      note: 'The employer page said the application was received.',
    })
  })
})
