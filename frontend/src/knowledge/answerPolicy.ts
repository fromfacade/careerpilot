import type { AnswerCategory, AnswerStatus } from '../api/types'

export const SENSITIVE_CATEGORIES: ReadonlySet<AnswerCategory> = new Set([
  'work_authorization',
  'sponsorship',
  'disability',
  'veteran',
  'demographic',
  'criminal_history',
  'legal_attestation',
  'salary',
])

export function isSensitiveCategory(category: AnswerCategory): boolean {
  return SENSITIVE_CATEGORIES.has(category)
}

/** Sensitive drafts cannot skip the reviewed step. */
export function nextStatusAfterApproveClick(category: AnswerCategory, status: AnswerStatus): AnswerStatus | null {
  if (status === 'approved') return null
  if (isSensitiveCategory(category) && status === 'draft') return 'reviewed'
  return 'approved'
}
