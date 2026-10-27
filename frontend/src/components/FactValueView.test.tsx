import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { CandidateFact, FactType, FactVerificationStatus } from '../api/types'
import { FactValueView, ReviewNotice } from './FactValueView'

function fact(
  fact_type: FactType,
  fact_value: Record<string, unknown>,
  verification_status: FactVerificationStatus = 'unverified',
): CandidateFact {
  return {
    id: 1,
    candidate_id: 1,
    resume_id: 1,
    fact_type,
    fact_key: 'k',
    fact_value,
    raw_text: null,
    source: 'resume_extraction',
    verification_status,
    verified_at: null,
    created_at: '2026-10-26T00:00:00Z',
    updated_at: '2026-10-26T00:00:00Z',
  }
}

describe('FactValueView', () => {
  afterEach(() => cleanup())

  it('renders a whole job: employer, position, location, dates, and every bullet', () => {
    render(
      <FactValueView
        fact={fact('work_experience', {
          employer: 'Northwind Tutoring Services',
          position: 'Student Office Assistant',
          location: 'Springfield, ST',
          dates_text: 'September 2024 – Present',
          bullets: ['Built a tracker.', 'Analyzed trends.', 'Documented workflows.'],
        })}
      />,
    )
    expect(screen.getByText('Northwind Tutoring Services')).toBeInTheDocument()
    expect(screen.getByText('Student Office Assistant')).toBeInTheDocument()
    expect(screen.getByText('Springfield, ST')).toBeInTheDocument()
    expect(screen.getByText('September 2024 – Present')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
  })

  it('renders a project with its subtitle, labelled technologies, and bullets', () => {
    render(
      <FactValueView
        fact={fact('project', {
          name: 'Alpha Queue',
          tagline: 'Backend Job Platform',
          technologies: ['Python', 'FastAPI'],
          bullets: ['One.', 'Two.'],
        })}
      />,
    )
    expect(screen.getByText('Backend Job Platform')).toBeInTheDocument()
    const tech = screen.getByLabelText('Technologies')
    expect(tech).toHaveTextContent('Python')
    expect(tech).toHaveTextContent('FastAPI')
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('marks an undetermined field and shows the unclassified header text', () => {
    render(
      <FactValueView
        fact={fact('work_experience', {
          employer: null,
          position: null,
          location: 'Tulsa, OK',
          unclassified_text: ['Omega Works', 'Wizard'],
          needs_review: true,
          ambiguous_fields: ['employer', 'position'],
          bullets: ['Filed records.'],
        })}
      />,
    )
    expect(screen.getAllByText('Not determined')).toHaveLength(2)
    expect(screen.getAllByText('(check)')).toHaveLength(2)
    expect(screen.getByText(/Omega Works \/ Wizard/)).toBeInTheDocument()
  })

  it('renders skill categories as chips without a technologies label', () => {
    render(<FactValueView fact={fact('skill', { items: ['Python', 'SQL'] })} />)
    expect(screen.getByLabelText('Skills')).toHaveTextContent('Python')
    expect(screen.queryByLabelText('Technologies')).not.toBeInTheDocument()
  })
})

describe('ReviewNotice', () => {
  afterEach(() => cleanup())

  const flagged = {
    needs_review: true,
    review_reasons: ['Employer carried over from the preceding position; confirm it applies.'],
    ambiguous_fields: ['employer'],
  }

  it('lists why the parser was unsure and says bulk verify skips it', () => {
    render(<ReviewNotice fact={fact('work_experience', flagged)} />)
    expect(screen.getByRole('note')).toBeInTheDocument()
    expect(screen.getByText(/employer carried over/i)).toBeInTheDocument()
    expect(screen.getByText(/skipped by/i)).toBeInTheDocument()
  })

  it('disappears once a human has made a decision', () => {
    for (const status of ['verified', 'edited', 'rejected'] as const) {
      const { unmount } = render(<ReviewNotice fact={fact('work_experience', flagged, status)} />)
      expect(screen.queryByRole('note')).not.toBeInTheDocument()
      unmount()
    }
  })

  it('renders nothing for an unflagged record', () => {
    render(<ReviewNotice fact={fact('work_experience', { employer: 'Acme' })} />)
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })
})
