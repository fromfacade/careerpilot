import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ApplicationPreparation } from '../api/types'
import { ApplicationPreparationPanel } from './ApplicationPreparationPanel'

vi.mock('../api/client', () => ({
  api: {
    listPreparations: vi.fn(),
    listResumes: vi.fn(),
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
    expect(screen.getAllByText(/Application needs review/).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: /submit/i })).not.toBeInTheDocument()
  })
})
