import { describe, expect, it } from 'vitest'
import type { CandidateFact, FactType } from '../api/types'
import { applyFieldValue, EDITABLE_FIELDS, fieldValue, summaryRows } from './factFields'

function fact(fact_type: FactType, fact_value: Record<string, unknown>): CandidateFact {
  return {
    id: 1,
    candidate_id: 1,
    resume_id: 1,
    fact_type,
    fact_key: 'k',
    fact_value,
    raw_text: null,
    source: 'resume_extraction',
    verification_status: 'unverified',
    verified_at: null,
    created_at: '2026-10-26T00:00:00Z',
    updated_at: '2026-10-26T00:00:00Z',
  }
}

describe('summaryRows', () => {
  it('shows work location and dates alongside employer and position', () => {
    const rows = summaryRows(
      fact('work_experience', {
        employer: 'Northwind',
        position: 'Assistant',
        location: 'Springfield, ST',
        dates_text: 'September 2024 – Present',
      }),
    )
    expect(rows.map((r) => [r.label, r.value])).toEqual([
      ['Employer', 'Northwind'],
      ['Position', 'Assistant'],
      ['Location', 'Springfield, ST'],
      ['Dates', 'September 2024 – Present'],
    ])
    expect(rows.every((r) => !r.ambiguous)).toBe(true)
  })

  it('shows a project subtitle separately from its name', () => {
    const rows = summaryRows(fact('project', { name: 'Alpha Queue', tagline: 'Job Processing Platform' }))
    expect(rows.map((r) => [r.label, r.value])).toEqual([
      ['Project', 'Alpha Queue'],
      ['Subtitle', 'Job Processing Platform'],
    ])
  })

  it('makes an undetermined flagged field visible instead of silently blank', () => {
    const rows = summaryRows(
      fact('work_experience', {
        employer: null,
        position: null,
        location: 'Tulsa, OK',
        needs_review: true,
        ambiguous_fields: ['employer', 'position'],
      }),
    )
    const byLabel = Object.fromEntries(rows.map((r) => [r.label, r]))
    expect(byLabel.Employer).toMatchObject({ value: 'Not determined', ambiguous: true })
    expect(byLabel.Position).toMatchObject({ value: 'Not determined', ambiguous: true })
    expect(byLabel.Location).toMatchObject({ value: 'Tulsa, OK', ambiguous: false })
  })

  it('omits unflagged empty optional fields rather than inventing values', () => {
    const rows = summaryRows(fact('work_experience', { employer: 'Solo', position: 'Designer', location: null }))
    expect(rows.map((r) => r.label)).toEqual(['Employer', 'Position'])
  })

  it('flags a present-but-inferred value for checking', () => {
    const rows = summaryRows(
      fact('work_experience', { employer: 'Acme', position: 'Intern', needs_review: true, ambiguous_fields: ['employer'] }),
    )
    expect(rows.find((r) => r.label === 'Employer')).toMatchObject({ value: 'Acme', ambiguous: true })
  })
})

describe('field editing helpers', () => {
  it('round-trips comma lists and line lists', () => {
    const projectFields = EDITABLE_FIELDS.project!
    const tech = projectFields.find((f) => f.key === 'technologies')!
    const bullets = projectFields.find((f) => f.key === 'bullets')!
    const original = fact('project', { technologies: ['Python', 'FastAPI'], bullets: ['One.', 'Two.'] })
    expect(fieldValue(original, tech)).toBe('Python, FastAPI')
    expect(fieldValue(original, bullets)).toBe('One.\nTwo.')

    const edited = applyFieldValue(applyFieldValue({}, tech, 'Python,  Go , '), bullets, 'A\n\nB')
    expect(edited).toEqual({ technologies: ['Python', 'Go'], bullets: ['A', 'B'] })
  })

  it('stores a cleared text field as null, not an empty string', () => {
    const location = EDITABLE_FIELDS.work_experience!.find((f) => f.key === 'location')!
    expect(applyFieldValue({ location: 'X' }, location, '   ')).toEqual({ location: null })
  })

  it('exposes work location and project subtitle for editing', () => {
    expect(EDITABLE_FIELDS.work_experience!.map((f) => f.key)).toContain('location')
    expect(EDITABLE_FIELDS.project!.map((f) => f.key)).toContain('tagline')
  })
})
