import { describe, expect, it } from 'vitest'
import { looksLikeSerializedJson, resumeBullets, resumeHeading, resumeMeta } from './resumePreview'

describe('resumePreview', () => {
  it('formats work and project details without serialized JSON', () => {
    const work = {
      employer: 'Northwind Tutoring',
      position: 'Office Assistant',
      dates_text: '2024 – Present',
      bullets: ['Built a tracker.', 'Documented workflows.'],
      review_reasons: ['ignore'],
    }
    expect(resumeHeading('work_experience', 'Northwind', work)).toBe('Office Assistant — Northwind Tutoring')
    expect(resumeMeta('work_experience', work)).toEqual([{ label: 'Dates', value: '2024 – Present' }])
    expect(resumeBullets(work)).toEqual(['Built a tracker.', 'Documented workflows.'])
    expect(looksLikeSerializedJson(JSON.stringify(work))).toBe(true)
    expect(looksLikeSerializedJson(resumeHeading('work_experience', 'Northwind', work))).toBe(false)

    const project = { name: 'Alpha Queue', technologies: ['FastAPI', 'Redis'], bullets: ['Queued jobs.'] }
    expect(resumeHeading('projects', 'Alpha Queue', project)).toBe('Alpha Queue')
    expect(resumeMeta('projects', project)).toEqual([{ label: 'Technologies', value: 'FastAPI, Redis' }])
    expect(resumeBullets(project)).toEqual(['Queued jobs.'])
  })
})
