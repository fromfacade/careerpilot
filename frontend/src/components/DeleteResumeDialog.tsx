import { useState } from 'react'
import type { Resume } from '../api/types'
import { deletionRequiresReplacement, replacementCandidates } from '../resume/deletePolicy'

export function DeleteResumeDialog({
  resume,
  allResumes,
  busy,
  error,
  onCancel,
  onConfirm,
}: {
  resume: Resume
  allResumes: Resume[]
  busy: boolean
  error: string | null
  onCancel: () => void
  onConfirm: (options: { deleteVerifiedFacts: boolean; replacementResumeId: number | null }) => void
}) {
  const needsReplacement = deletionRequiresReplacement(resume, allResumes)
  const others = replacementCandidates(resume, allResumes)
  const [deleteVerifiedFacts, setDeleteVerifiedFacts] = useState(false)
  const [replacementResumeId, setReplacementResumeId] = useState<number | ''>(others[0]?.id ?? '')

  function handleConfirm() {
    if (needsReplacement && replacementResumeId === '') return
    onConfirm({
      deleteVerifiedFacts,
      replacementResumeId: needsReplacement && typeof replacementResumeId === 'number' ? replacementResumeId : null,
    })
  }

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-slate-900/40 p-4" role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={`delete-resume-title-${resume.id}`}
        className="w-full max-w-lg rounded-lg border border-slate-200 bg-white p-4 shadow-lg"
      >
        <h3 id={`delete-resume-title-${resume.id}`} className="text-base font-semibold text-slate-900">
          Delete {resume.original_filename}?
        </h3>
        <p className="mt-2 text-sm text-slate-700">
          This removes only the selected uploaded file and the extracted records that belong to
          it. Job listings, preferences, and saved jobs are not changed.
        </p>
        <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-slate-700">
          <li>Unverified and rejected records extracted from this file will be deleted.</li>
          <li>
            Records extracted from other resumes stay attached to those files and are not deleted.
          </li>
          <li>
            Independently verified or edited candidate records from this file are kept by default.
            They become resume-independent facts instead of being removed.
          </li>
        </ul>
        <label className="mt-3 flex items-start gap-2 text-sm text-slate-800">
          <input
            type="checkbox"
            className="mt-1"
            checked={deleteVerifiedFacts}
            onChange={(e) => setDeleteVerifiedFacts(e.target.checked)}
          />
          <span>Also delete verified and edited records that came from this resume.</span>
        </label>
        {needsReplacement && (
          <label className="mt-3 block text-sm">
            <span className="font-medium text-slate-800">
              This is the primary resume. Choose another file to use as primary.
            </span>
            <select
              value={replacementResumeId}
              onChange={(e) => setReplacementResumeId(e.target.value === '' ? '' : Number(e.target.value))}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
              required
            >
              {others.map((other) => (
                <option key={other.id} value={other.id}>
                  {other.original_filename}
                </option>
              ))}
            </select>
          </label>
        )}
        {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={onCancel}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={busy || (needsReplacement && replacementResumeId === '')}
            onClick={handleConfirm}
            className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
          >
            {busy ? 'Deleting…' : 'Delete resume'}
          </button>
        </div>
      </div>
    </div>
  )
}
