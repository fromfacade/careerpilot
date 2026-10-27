import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Resume } from '../api/types'
import { DeleteResumeDialog } from './DeleteResumeDialog'

function resume(partial: Partial<Resume> & Pick<Resume, 'id' | 'is_primary' | 'original_filename'>): Resume {
  return {
    candidate_id: 1,
    file_format: 'pdf',
    file_size_bytes: 100,
    sha256_checksum: 'abc',
    parse_status: 'success',
    parse_error: null,
    created_at: '2026-10-26T00:00:00Z',
    ...partial,
  }
}

describe('DeleteResumeDialog', () => {
  afterEach(() => cleanup())

  const primary = resume({ id: 1, is_primary: true, original_filename: 'primary.pdf' })
  const other = resume({ id: 2, is_primary: false, original_filename: 'other.pdf' })

  it('explains record isolation and that jobs/preferences are untouched', () => {
    render(
      <DeleteResumeDialog resume={other} allResumes={[primary, other]} busy={false} error={null} onCancel={vi.fn()} onConfirm={vi.fn()} />,
    )
    expect(screen.getByRole('dialog', { name: /delete other.pdf/i })).toBeInTheDocument()
    expect(screen.getByText(/job listings, preferences, and saved jobs are not changed/i)).toBeInTheDocument()
    expect(screen.getByText(/records extracted from other resumes stay attached/i)).toBeInTheDocument()
    expect(screen.getByText(/independently verified or edited candidate records/i)).toBeInTheDocument()
    expect(screen.queryByLabelText(/choose another file to use as primary/i)).not.toBeInTheDocument()
  })

  it('asks for a replacement when the primary resume is deleted', () => {
    const onConfirm = vi.fn()
    render(
      <DeleteResumeDialog resume={primary} allResumes={[primary, other]} busy={false} error={null} onCancel={vi.fn()} onConfirm={onConfirm} />,
    )
    expect(screen.getByLabelText(/choose another file to use as primary/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /delete resume/i }))
    expect(onConfirm).toHaveBeenCalledWith({ deleteVerifiedFacts: false, replacementResumeId: 2 })
  })

  it('sends the explicit choice to also delete verified records', () => {
    const onConfirm = vi.fn()
    render(
      <DeleteResumeDialog resume={other} allResumes={[primary, other]} busy={false} error={null} onCancel={vi.fn()} onConfirm={onConfirm} />,
    )
    fireEvent.click(screen.getByLabelText(/also delete verified and edited records/i))
    fireEvent.click(screen.getByRole('button', { name: /delete resume/i }))
    expect(onConfirm).toHaveBeenCalledWith({ deleteVerifiedFacts: true, replacementResumeId: null })
  })
})
