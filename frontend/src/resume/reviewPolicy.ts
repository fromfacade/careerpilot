import type { CandidateFact } from '../api/types'

/**
 * Review flags written by the backend parser into `fact_value`:
 *   needs_review: true when the parser could not confidently assign a field
 *   review_reasons: human-readable explanations
 *   ambiguous_fields: names of the fields the reviewer must check
 *
 * Nothing here ever verifies a fact. These helpers only decide what the UI
 * may offer; the backend independently refuses to bulk-verify flagged facts.
 */

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

export function needsReview(fact: CandidateFact): boolean {
  return fact.fact_value.needs_review === true
}

export function reviewReasons(fact: CandidateFact): string[] {
  return stringList(fact.fact_value.review_reasons)
}

export function ambiguousFields(fact: CandidateFact): string[] {
  return stringList(fact.fact_value.ambiguous_fields)
}

export function isFieldAmbiguous(fact: CandidateFact, key: string): boolean {
  return ambiguousFields(fact).includes(key)
}

/** A flagged fact only keeps nagging until a human has made a decision on it. */
export function awaitsReview(fact: CandidateFact): boolean {
  return needsReview(fact) && fact.verification_status === 'unverified'
}

/**
 * Split a bulk selection into facts that may be verified in one action and
 * facts that must be reviewed one at a time. Flagged facts that are still
 * unreviewed are never bulk-verified.
 */
export function splitBulkVerifiable(
  facts: CandidateFact[],
  selectedIds: ReadonlySet<number>,
): { verifiableIds: number[]; blocked: CandidateFact[] } {
  const verifiableIds: number[] = []
  const blocked: CandidateFact[] = []
  for (const fact of facts) {
    if (!selectedIds.has(fact.id)) continue
    if (needsReview(fact)) blocked.push(fact)
    else verifiableIds.push(fact.id)
  }
  return { verifiableIds, blocked }
}
