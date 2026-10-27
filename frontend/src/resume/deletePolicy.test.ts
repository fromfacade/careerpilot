import { describe, expect, it } from 'vitest'
import type { Resume } from '../api/types'
import { deletionRequiresReplacement, replacementCandidates } from './deletePolicy'

function resume(partial: Partial<Resume> & Pick<Resume, 'id' | 'is_primary'>): Resume {
  return {
    candidate_id: 1,
    original_filename: `resume-${partial.id}.pdf`,
    file_format: 'pdf',
    file_size_bytes: 100,
    sha256_checksum: 'abc',
    parse_status: 'success',
    parse_error: null,
    profile_name: `resume-${partial.id}`,
    profile_description: '',
    category: 'custom',
    is_approved: false,
    is_archived: false,
    focus_areas: [],
    created_at: '2026-10-26T00:00:00Z',
    updated_at: '2026-10-26T00:00:00Z',
    ...partial,
  }
}

describe('deletionRequiresReplacement', () => {
  it('requires a replacement only when deleting the primary while others exist', () => {
    const primary = resume({ id: 1, is_primary: true })
    const other = resume({ id: 2, is_primary: false })
    expect(deletionRequiresReplacement(primary, [primary, other])).toBe(true)
    expect(deletionRequiresReplacement(other, [primary, other])).toBe(false)
    expect(deletionRequiresReplacement(primary, [primary])).toBe(false)
  })
})

describe('replacementCandidates', () => {
  it('returns every resume except the one being deleted', () => {
    const primary = resume({ id: 1, is_primary: true, original_filename: 'primary.pdf' })
    const other = resume({ id: 2, is_primary: false, original_filename: 'other.pdf' })
    expect(replacementCandidates(primary, [primary, other])).toEqual([other])
  })
})
