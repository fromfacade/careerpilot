import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AutoApplySettings } from '../api/types'
import { AutoApplyPanel } from './AutoApplyPanel'

vi.mock('virtual:careerpilot-token', () => ({ default: 'test-token' }))

vi.mock('../api/client', () => ({
  api: {
    getCandidate: vi.fn(),
    getAutoApply: vi.fn(),
    updateAutoApply: vi.fn(),
    listResumes: vi.fn(),
  },
}))

import { api } from '../api/client'

const explanation =
  'Auto-Apply allows CareerPilot to submit eligible, complete applications automatically within your configured limits.'

const settings: AutoApplySettings = {
  mode: 'review',
  enabled: false,
  acknowledged: false,
  active: false,
  inactive_reason: 'Auto-Apply is off.',
  provider: 'greenhouse',
  job_categories: ['swe_backend'],
  employment_types: ['internship'],
  locations: ['Santa Cruz, CA'],
  min_match_score: 70,
  max_per_day: 5,
  max_per_session: 2,
  resumes: [{ id: 4, profile_name: 'Fictional backend profile', is_approved: true }],
  expires_at: null,
  explanation,
  automatic_submission: false,
}

describe('AutoApplyPanel', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('shows Review Mode until the user acknowledges Auto-Apply', async () => {
    vi.mocked(api.getCandidate).mockResolvedValue({ id: 1 } as never)
    vi.mocked(api.getAutoApply).mockResolvedValue(settings)
    vi.mocked(api.listResumes).mockResolvedValue([])
    vi.mocked(api.updateAutoApply).mockResolvedValue({ ...settings, enabled: true, active: true, mode: 'auto_apply' })

    render(<AutoApplyPanel />)

    expect(await screen.findByText('Review')).toBeTruthy()
    expect(screen.getByText(explanation)).toBeTruthy()
    expect(screen.getByText('Auto-Apply is not active. Review Mode asks you to confirm each job.')).toBeTruthy()
    expect(screen.getByText('5')).toBeTruthy()
    expect(screen.getByText('Fictional backend profile')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Enable Auto-Apply' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save Auto-Apply' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('acknowledgement')
    expect(api.updateAutoApply).not.toHaveBeenCalled()

    fireEvent.click(
      screen.getByRole('checkbox', {
        name: /Auto-Apply allows CareerPilot to submit eligible, complete applications/,
      }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Save Auto-Apply' }))

    await waitFor(() => expect(api.updateAutoApply).toHaveBeenCalled())
    const payload = vi.mocked(api.updateAutoApply).mock.calls[0][0]
    expect(payload.enabled).toBe(true)
    expect(payload.acknowledge).toBe(true)
    expect(payload.provider).toBe('greenhouse')
    expect(payload.job_categories).toEqual(['swe_backend'])
    expect(payload.locations).toEqual(['Santa Cruz, CA'])
  })
})
