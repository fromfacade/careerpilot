import { describe, expect, it } from 'vitest'
import type { CandidateFact, FactVerificationStatus } from '../api/types'
import { ambiguousFields, awaitsReview, isFieldAmbiguous, needsReview, reviewReasons, splitBulkVerifiable } from './reviewPolicy'

function fact(id: number, value: Record<string, unknown>, status: FactVerificationStatus = 'unverified'): CandidateFact {
  return {
    id,
    candidate_id: 1,
    resume_id: 1,
    fact_type: 'work_experience',
    fact_key: `fact-${id}`,
    fact_value: value,
    raw_text: null,
    source: 'resume_extraction',
    verification_status: status,
    verified_at: null,
    created_at: '2026-10-26T00:00:00Z',
    updated_at: '2026-10-26T00:00:00Z',
  }
}

const flagged = { needs_review: true, review_reasons: ['Could not tell the employer from the position'], ambiguous_fields: ['employer', 'position'] }

describe('reviewPolicy', () => {
  it('reads the parser review flags and tolerates their absence', () => {
    expect(needsReview(fact(1, flagged))).toBe(true)
    expect(reviewReasons(fact(1, flagged))).toEqual(['Could not tell the employer from the position'])
    expect(ambiguousFields(fact(1, flagged))).toEqual(['employer', 'position'])
    expect(isFieldAmbiguous(fact(1, flagged), 'employer')).toBe(true)
    expect(isFieldAmbiguous(fact(1, flagged), 'location')).toBe(false)

    const plain = fact(2, { employer: 'Acme' })
    expect(needsReview(plain)).toBe(false)
    expect(reviewReasons(plain)).toEqual([])
    expect(ambiguousFields(plain)).toEqual([])
  })

  it('ignores malformed flag payloads instead of crashing', () => {
    const odd = fact(3, { needs_review: 'yes', review_reasons: 'nope', ambiguous_fields: [1, 'employer'] })
    expect(needsReview(odd)).toBe(false)
    expect(reviewReasons(odd)).toEqual([])
    expect(ambiguousFields(odd)).toEqual(['employer'])
  })

  it('only nags while a flagged record is still unreviewed', () => {
    expect(awaitsReview(fact(1, flagged, 'unverified'))).toBe(true)
    expect(awaitsReview(fact(1, flagged, 'verified'))).toBe(false)
    expect(awaitsReview(fact(1, flagged, 'edited'))).toBe(false)
    expect(awaitsReview(fact(1, flagged, 'rejected'))).toBe(false)
    expect(awaitsReview(fact(2, {}, 'unverified'))).toBe(false)
  })

  it('never offers flagged records for bulk verification', () => {
    const facts = [fact(1, { employer: 'A' }), fact(2, flagged), fact(3, { employer: 'C' }), fact(4, flagged)]
    const result = splitBulkVerifiable(facts, new Set([1, 2, 3]))
    expect(result.verifiableIds).toEqual([1, 3])
    expect(result.blocked.map((f) => f.id)).toEqual([2])
  })

  it('returns nothing for an empty selection or when everything is flagged', () => {
    const facts = [fact(1, flagged), fact(2, flagged)]
    expect(splitBulkVerifiable(facts, new Set())).toEqual({ verifiableIds: [], blocked: [] })
    expect(splitBulkVerifiable(facts, new Set([1, 2])).verifiableIds).toEqual([])
  })
})
