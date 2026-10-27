import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ApplicationPreparation, AutofillSession } from '../api/types'
import { AutofillReview } from './AutofillReview'

vi.mock('../api/client', () => ({
  api: {
    openAutofillSession: vi.fn(),
    fillAutofillSession: vi.fn(),
    cancelAutofillSession: vi.fn(),
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
  afterEach(() => cleanup())

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
    expect(screen.getByText('Phone')).toBeInTheDocument()
    expect(screen.getByText('Work authorization')).toBeInTheDocument()
    expect(screen.getByText('School')).toBeInTheDocument()
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
})
