import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ApplicationPreparation } from '../api/types'

vi.mock('virtual:careerpilot-token', () => ({ default: '' }))
vi.mock('../api/client', () => ({
  api: {
    openAutofillSession: vi.fn(),
    fillAutofillSession: vi.fn(),
    cancelAutofillSession: vi.fn(),
  },
}))

import { AutofillReview } from './AutofillReview'

describe('AutofillReview token configuration', () => {
  afterEach(() => cleanup())

  it('keeps the controls visible when the local token is missing', () => {
    render(
      <AutofillReview
        prep={
          {
            snapshot_job_title: 'Intern',
            snapshot_employer: 'Northwind',
            snapshot_apply_url: 'https://boards.greenhouse.io/northwind/jobs/15',
            greenhouse_apply_url: 'https://boards.greenhouse.io/northwind/jobs/15',
            greenhouse_autofill_note: '',
          } as unknown as ApplicationPreparation
        }
      />,
    )
    expect(screen.getByRole('button', { name: 'Apply with CareerPilot' })).toBeInTheDocument()
    expect(screen.getByText(/local API token is not loaded/)).toBeInTheDocument()
  })
})
