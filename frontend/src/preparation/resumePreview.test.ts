import { describe, expect, it } from 'vitest'
import {
  looksLikeInternalLabel,
  looksLikeSerializedJson,
  resumeBullets,
  resumeHeading,
  resumeSubline,
} from './resumePreview'

describe('resumePreview', () => {
  it('formats work and project details without labels or serialized JSON', () => {
    const work = {
      employer: 'Northwind Tutoring',
      position: 'Office Assistant',
      dates_text: '2024 – Present',
      bullets: ['Built a tracker.', 'Documented workflows.'],
      review_reasons: ['ignore'],
    }
    expect(resumeHeading('work_experience', 'Northwind', work)).toBe('Office Assistant - Northwind Tutoring')
    expect(resumeSubline('work_experience', work)).toBe('2024 - Present')
    expect(resumeBullets(work)).toEqual(['Built a tracker.', 'Documented workflows.'])
    expect(looksLikeSerializedJson(JSON.stringify(work))).toBe(true)
    expect(looksLikeSerializedJson(resumeHeading('work_experience', 'Northwind', work))).toBe(false)
    expect(looksLikeInternalLabel(resumeSubline('work_experience', work))).toBe(false)

    const project = { name: 'Alpha Queue', technologies: ['FastAPI', 'Redis'], bullets: ['Queued jobs.'] }
    expect(resumeHeading('projects', 'Alpha Queue', project)).toBe('Alpha Queue')
    expect(resumeSubline('projects', project)).toBe('FastAPI, Redis')
    expect(resumeBullets(project)).toEqual(['Queued jobs.'])
    expect(looksLikeInternalLabel('Technologies: FastAPI')).toBe(true)
    expect(looksLikeInternalLabel('Dates: 2024')).toBe(true)
  })
})
