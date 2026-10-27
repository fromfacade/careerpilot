import { describe, expect, it } from 'vitest'
import { isSensitiveCategory, nextStatusAfterApproveClick } from './answerPolicy'

describe('answerPolicy', () => {
  it('treats authorization and salary as sensitive, not projects', () => {
    expect(isSensitiveCategory('work_authorization')).toBe(true)
    expect(isSensitiveCategory('salary')).toBe(true)
    expect(isSensitiveCategory('experience')).toBe(false)
  })

  it('forces a review step for sensitive drafts', () => {
    expect(nextStatusAfterApproveClick('work_authorization', 'draft')).toBe('reviewed')
    expect(nextStatusAfterApproveClick('work_authorization', 'reviewed')).toBe('approved')
    expect(nextStatusAfterApproveClick('interest', 'draft')).toBe('approved')
  })
})
