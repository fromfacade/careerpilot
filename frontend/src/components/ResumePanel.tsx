import { useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import type { CandidateFact, FactType, FactVerificationStatus, Resume, ResumeCategory, ResumeUploadResult } from '../api/types'
import { useFetch } from '../hooks/useFetch'
import { Badge } from './Badge'
import { applyFieldValue, EDITABLE_FIELDS, fieldValue, isCommaList } from '../resume/factFields'
import { awaitsReview, isFieldAmbiguous, splitBulkVerifiable } from '../resume/reviewPolicy'
import { DeleteResumeDialog } from './DeleteResumeDialog'
import { FactValueView, ReviewNotice } from './FactValueView'
import { EmptyBlock, ErrorBlock, LoadingBlock } from './StatusViews'

const CATEGORY_LABEL: Record<ResumeCategory, string> = {
  general_swe: 'General SWE',
  backend: 'Backend',
  fullstack: 'Full-stack',
  ai_ml: 'AI / ML',
  custom: 'Custom',
}

const PARSE_STATUS_TONE: Record<Resume['parse_status'], 'green' | 'red' | 'amber' | 'slate'> = {
  pending: 'slate',
  success: 'green',
  partial: 'amber',
  failed: 'red',
}

const FACT_TYPE_LABEL: Record<FactType, string> = {
  education: 'Education',
  skill: 'Skill',
  project: 'Project',
  work_experience: 'Work experience',
  achievement: 'Achievement',
  other: 'Unstructured',
}

const FACT_TYPE_ORDER: FactType[] = [
  'education',
  'work_experience',
  'project',
  'skill',
  'achievement',
  'other',
]

const VERIFICATION_TONE: Record<FactVerificationStatus, 'green' | 'red' | 'amber' | 'blue' | 'slate'> = {
  unverified: 'slate',
  verified: 'green',
  edited: 'blue',
  rejected: 'red',
}

function formatDate(value: string | null): string {
  if (!value) return 'unknown'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

function FactCard({
  fact,
  selected,
  onToggle,
  onChanged,
}: {
  fact: CandidateFact
  selected: boolean
  onToggle: () => void
  onChanged: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [editKey, setEditKey] = useState(fact.fact_key)
  const [editFields, setEditFields] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const fields = EDITABLE_FIELDS[fact.fact_type] ?? []

  function startEdit() {
    setEditKey(fact.fact_key)
    const next: Record<string, string> = {}
    for (const field of fields) next[field.key] = fieldValue(fact, field)
    setEditFields(next)
    setEditing(true)
  }

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    try {
      await action()
      onChanged()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  async function handleSaveEdit() {
    let fact_value: Record<string, unknown> = { ...fact.fact_value }
    for (const field of fields) {
      fact_value = applyFieldValue(fact_value, field, editFields[field.key] ?? '')
    }
    await run(async () => {
      await api.updateCandidateFact(fact.id, { fact_key: editKey, fact_value })
      setEditing(false)
    })
  }

  return (
    <li className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            className="mt-1"
            aria-label={`Select ${fact.fact_key}`}
          />
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="blue">{FACT_TYPE_LABEL[fact.fact_type]}</Badge>
              <Badge tone={VERIFICATION_TONE[fact.verification_status]}>{fact.verification_status}</Badge>
              {awaitsReview(fact) && <Badge tone="amber">Needs review</Badge>}
            </div>
            {!editing && <h4 className="mt-1 text-sm font-semibold text-slate-900">{fact.fact_key}</h4>}
          </div>
        </label>
      </div>

      {!editing && <ReviewNotice fact={fact} />}
      {!editing && <FactValueView fact={fact} />}

      {editing && (
        <div className="mt-2 space-y-2">
          <label className="block text-xs">
            <span className="font-medium text-slate-700">Label</span>
            <input
              value={editKey}
              onChange={(e) => setEditKey(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
          {fields.map((field) => (
            <label key={field.key} className="block text-xs">
              <span className="font-medium text-slate-700">
                {field.label}
                {isFieldAmbiguous(fact, field.key) && (
                  <span className="ml-1 font-semibold text-amber-700">(check this field)</span>
                )}
              </span>
              {field.kind === 'list' && !isCommaList(field) ? (
                <textarea
                  value={editFields[field.key] ?? ''}
                  onChange={(e) => setEditFields((prev) => ({ ...prev, [field.key]: e.target.value }))}
                  rows={3}
                  className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
                />
              ) : (
                <input
                  value={editFields[field.key] ?? ''}
                  onChange={(e) => setEditFields((prev) => ({ ...prev, [field.key]: e.target.value }))}
                  className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
                />
              )}
            </label>
          ))}
        </div>
      )}

      {fact.raw_text && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs font-medium text-blue-700">Show original extracted text</summary>
          <pre className="mt-1 whitespace-pre-wrap rounded-md bg-slate-50 p-2 text-xs text-slate-600">{fact.raw_text}</pre>
        </details>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {editing ? (
          <>
            <button
              type="button"
              disabled={busy}
              onClick={handleSaveEdit}
              className="rounded-md bg-blue-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Save edit
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => setEditing(false)}
              className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              disabled={busy || fact.verification_status === 'verified'}
              onClick={() => run(() => api.updateCandidateFact(fact.id, { verification_status: 'verified' }))}
              className="rounded-md border border-green-300 px-2.5 py-1 text-xs font-medium text-green-700 hover:bg-green-50 disabled:opacity-50"
            >
              Verify entire record
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={startEdit}
              className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              Edit fields
            </button>
            <button
              type="button"
              disabled={busy || fact.verification_status === 'rejected'}
              onClick={() => run(() => api.updateCandidateFact(fact.id, { verification_status: 'rejected' }))}
              className="rounded-md border border-red-300 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
            >
              Reject
            </button>
          </>
        )}
      </div>
    </li>
  )
}

export function ResumePanel() {
  const resumes = useFetch(() => api.listResumes())
  const [factTypeFilter, setFactTypeFilter] = useState<FactType | ''>('')
  const [statusFilter, setStatusFilter] = useState<FactVerificationStatus | ''>('')
  const facts = useFetch(
    () =>
      api.listCandidateFacts({
        fact_type: factTypeFilter || undefined,
        verification_status: statusFilter || undefined,
      }),
    [factTypeFilter, statusFilter],
  )

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [lastUpload, setLastUpload] = useState<ResumeUploadResult | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [bulkBusy, setBulkBusy] = useState(false)
  const [reprocessBusyId, setReprocessBusyId] = useState<number | null>(null)
  const [reprocessMessage, setReprocessMessage] = useState<string | null>(null)
  const [bulkMessage, setBulkMessage] = useState<string | null>(null)
  const [primaryBusyId, setPrimaryBusyId] = useState<number | null>(null)
  const [resumePendingDelete, setResumePendingDelete] = useState<Resume | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null)

  const groupedFacts = useMemo(() => {
    const groups = new Map<FactType, CandidateFact[]>()
    if (facts.status !== 'success') return groups
    for (const fact of facts.data) {
      const list = groups.get(fact.fact_type) ?? []
      list.push(fact)
      groups.set(fact.fact_type, list)
    }
    return groups
  }, [facts])

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault()
    const file = fileInputRef.current?.files?.[0]
    if (!file) return

    setUploading(true)
    setUploadError(null)
    try {
      const result = await api.uploadResume(file)
      setLastUpload(result)
      if (fileInputRef.current) fileInputRef.current.value = ''
      setSelectedIds(new Set())
      resumes.reload()
      facts.reload()
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  async function handleReprocess(resumeId: number) {
    setReprocessBusyId(resumeId)
    setReprocessMessage(null)
    try {
      const result = await api.reprocessResume(resumeId)
      setSelectedIds(new Set())
      setReprocessMessage(
        `Reprocessed ${result.resume.original_filename}: ${result.facts_extracted} new fact(s), ${result.facts_replaced} unverified fact(s) replaced, ${result.facts_preserved} reviewed fact(s) kept, ${result.facts_skipped_duplicate} duplicate(s) of reviewed facts skipped.`,
      )
      resumes.reload()
      facts.reload()
    } catch (err) {
      setReprocessMessage(err instanceof Error ? err.message : 'Reprocess failed')
    } finally {
      setReprocessBusyId(null)
    }
  }

  async function handleSetPrimary(resumeId: number) {
    setPrimaryBusyId(resumeId)
    setDeleteMessage(null)
    try {
      await api.setPrimaryResume(resumeId)
      resumes.reload()
    } catch (err) {
      setDeleteMessage(err instanceof Error ? err.message : 'Could not set primary resume')
    } finally {
      setPrimaryBusyId(null)
    }
  }

  async function handleDeleteConfirm(options: { deleteVerifiedFacts: boolean; replacementResumeId: number | null }) {
    if (!resumePendingDelete) return
    setDeleteBusy(true)
    setDeleteError(null)
    try {
      const result = await api.deleteResume(resumePendingDelete.id, {
        delete_verified_facts: options.deleteVerifiedFacts,
        replacement_resume_id: options.replacementResumeId,
      })
      setDeleteMessage(
        `Deleted ${resumePendingDelete.original_filename}: ${result.facts_deleted} record(s) removed, ${result.facts_preserved} verified/edited record(s) kept.`,
      )
      setResumePendingDelete(null)
      setSelectedIds(new Set())
      resumes.reload()
      facts.reload()
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setDeleteBusy(false)
    }
  }

  async function handleBulk(status: 'verified' | 'rejected') {
    if (selectedIds.size === 0) return
    let ids = [...selectedIds]
    setBulkMessage(null)
    if (status === 'verified' && facts.status === 'success') {
      // Flagged (ambiguous / conflicting) records are never verified in bulk.
      const { verifiableIds, blocked } = splitBulkVerifiable(facts.data, selectedIds)
      ids = verifiableIds
      if (blocked.length > 0) {
        setBulkMessage(
          `${blocked.length} flagged record(s) were not verified: ${blocked
            .map((fact) => fact.fact_key)
            .join(', ')}. Review them individually.`,
        )
      }
      if (ids.length === 0) return
    }
    setBulkBusy(true)
    try {
      await api.bulkUpdateCandidateFacts({
        fact_ids: ids,
        verification_status: status,
      })
      setSelectedIds(new Set())
      facts.reload()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Bulk update failed')
    } finally {
      setBulkBusy(false)
    }
  }

  function toggleSelected(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const visibleIds = facts.status === 'success' ? facts.data.map((f) => f.id) : []

  return (
    <section aria-labelledby="resume-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="resume-heading" className="text-lg font-semibold text-slate-900">
        Resume &amp; verified facts
      </h2>
      <p className="mt-1 text-sm text-slate-500">
        Upload a PDF or DOCX resume. Education, skills, projects, work experience, and achievements are extracted
        deterministically (no AI, no network calls) into one reviewable record per school, job, project, or skill
        group. Nothing is marked verified until you say so. Uploaded files are kept immutable.
      </p>

      <form onSubmit={handleUpload} className="mt-3 flex flex-wrap items-center gap-2 border-b border-slate-100 pb-4">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx"
          required
          className="text-sm text-slate-700"
          aria-label="Resume file (PDF or DOCX)"
        />
        <button
          type="submit"
          disabled={uploading}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {uploading ? 'Uploading…' : 'Upload resume'}
        </button>
      </form>

      {uploadError && <ErrorBlock message={uploadError} />}
      {lastUpload && !uploadError && (
        <p className="mt-2 text-sm text-slate-700" role="status">
          {lastUpload.already_uploaded ? (
            <>
              <span className="font-medium">{lastUpload.resume.original_filename}</span> was already uploaded
              (identical file). Nothing was added or changed.
            </>
          ) : (
            <>
              Uploaded <span className="font-medium">{lastUpload.resume.original_filename}</span> —{' '}
              {lastUpload.resume.parse_status === 'success' && `${lastUpload.facts_extracted} record(s) extracted.`}
              {lastUpload.resume.parse_status === 'partial' &&
                `${lastUpload.facts_extracted} record(s) extracted, but some content didn't match a recognized resume section.`}
              {lastUpload.resume.parse_status === 'failed' &&
                `the file was saved, but parsing failed: ${lastUpload.resume.parse_error}`}
              {lastUpload.facts_skipped_duplicate > 0 &&
                ` ${lastUpload.facts_skipped_duplicate} record(s) matched ones you already verified and were not added again.`}
            </>
          )}
        </p>
      )}

      <h3 className="mt-4 text-sm font-semibold text-slate-900">Resume profiles</h3>
      {resumes.status === 'loading' && <LoadingBlock label="Loading resumes…" />}
      {resumes.status === 'error' && <ErrorBlock message={resumes.message} onRetry={resumes.reload} />}
      {resumes.status === 'success' && resumes.data.length === 0 && (
        <EmptyBlock message="No resumes uploaded yet." />
      )}
      {resumes.status === 'success' && resumes.data.length > 0 && (
        <ul className="mt-2 space-y-1.5">
          {resumes.data.map((r) => (
            <li
              key={r.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-slate-100 p-2 text-sm"
            >
              <span>
                <span className="font-medium">{r.profile_name || r.original_filename}</span>{' '}
                <span className="text-slate-500">({r.file_format.toUpperCase()})</span>
                <span className="mt-1 block text-xs text-slate-500">
                  {CATEGORY_LABEL[r.category]} · updated {formatDate(r.updated_at)}
                  {r.profile_description ? ` · ${r.profile_description}` : ''}
                </span>
                {r.is_primary && (
                  <span className="ml-0 mt-1 inline-block">
                    <Badge tone="blue">Default</Badge>
                  </span>
                )}
                {r.is_approved && (
                  <span className="ml-1">
                    <Badge tone="green">Approved</Badge>
                  </span>
                )}
                {r.is_archived && (
                  <span className="ml-1">
                    <Badge tone="amber">Archived</Badge>
                  </span>
                )}
              </span>
              <span className="flex flex-wrap items-center gap-2">
                <Badge tone={PARSE_STATUS_TONE[r.parse_status]}>{r.parse_status}</Badge>
                {r.parse_error && (
                  <span className="max-w-xs truncate text-xs text-red-700" title={r.parse_error}>
                    {r.parse_error}
                  </span>
                )}
                {!r.is_primary && (
                  <button
                    type="button"
                    disabled={primaryBusyId === r.id}
                    onClick={() => handleSetPrimary(r.id)}
                    className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                  >
                    {primaryBusyId === r.id ? 'Updating…' : 'Set as default'}
                  </button>
                )}
                <button
                  type="button"
                  disabled={primaryBusyId === r.id}
                  onClick={() =>
                    api.updateResumeProfile(r.id, { is_approved: !r.is_approved }).then(() => resumes.reload())
                  }
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  {r.is_approved ? 'Unapprove' : 'Approve'}
                </button>
                <button
                  type="button"
                  onClick={() =>
                    api.updateResumeProfile(r.id, { is_archived: !r.is_archived }).then(() => resumes.reload())
                  }
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  {r.is_archived ? 'Unarchive' : 'Archive'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const name = window.prompt('Resume profile name', r.profile_name || r.original_filename)
                    if (name?.trim()) {
                      void api.updateResumeProfile(r.id, { profile_name: name.trim() }).then(() => resumes.reload())
                    }
                  }}
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Rename
                </button>
                <select
                  aria-label={`Category for ${r.profile_name || r.original_filename}`}
                  value={r.category}
                  onChange={(event) => {
                    void api.updateResumeProfile(r.id, { category: event.target.value }).then(() => resumes.reload())
                  }}
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs"
                >
                  {Object.entries(CATEGORY_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => api.downloadResumeFile(r.id, r.original_filename)}
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Download
                </button>
                <button
                  type="button"
                  disabled={reprocessBusyId === r.id}
                  onClick={() => handleReprocess(r.id)}
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  {reprocessBusyId === r.id ? 'Reprocessing…' : 'Reprocess this file'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setDeleteError(null)
                    setResumePendingDelete(r)
                  }}
                  className="rounded-md border border-red-300 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
                >
                  Delete
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
      {reprocessMessage && (
        <p className="mt-2 text-sm text-slate-700" role="status">
          {reprocessMessage}
        </p>
      )}
      {deleteMessage && (
        <p className="mt-2 text-sm text-slate-700" role="status">
          {deleteMessage}
        </p>
      )}
      {resumePendingDelete && resumes.status === 'success' && (
        <DeleteResumeDialog
          resume={resumePendingDelete}
          allResumes={resumes.data}
          busy={deleteBusy}
          error={deleteError}
          onCancel={() => {
            if (!deleteBusy) {
              setResumePendingDelete(null)
              setDeleteError(null)
            }
          }}
          onConfirm={handleDeleteConfirm}
        />
      )}
      <p className="mt-2 text-xs text-slate-500">
        Reprocess re-reads the original stored file and replaces only unverified facts. Verified, edited, and rejected
        facts are kept. The uploaded file is never deleted.
      </p>

      <div className="mt-5 flex flex-wrap items-end justify-between gap-2 border-t border-slate-100 pt-4">
        <h3 className="text-sm font-semibold text-slate-900">Extracted records</h3>
        <div className="flex flex-wrap gap-2">
          <label className="text-xs">
            <span className="block font-medium text-slate-700">Type</span>
            <select
              value={factTypeFilter}
              onChange={(e) => setFactTypeFilter(e.target.value as FactType | '')}
              className="mt-1 rounded-md border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="">All types</option>
              {(Object.keys(FACT_TYPE_LABEL) as FactType[]).map((t) => (
                <option key={t} value={t}>
                  {FACT_TYPE_LABEL[t]}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs">
            <span className="block font-medium text-slate-700">Status</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as FactVerificationStatus | '')}
              className="mt-1 rounded-md border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="">All statuses</option>
              <option value="unverified">Unverified</option>
              <option value="verified">Verified</option>
              <option value="edited">Edited</option>
              <option value="rejected">Rejected</option>
            </select>
          </label>
        </div>
      </div>

      {facts.status === 'success' && facts.data.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-md bg-slate-50 p-2">
          <button
            type="button"
            className="text-xs font-medium text-blue-700 hover:underline"
            onClick={() => setSelectedIds(new Set(visibleIds))}
          >
            Select all visible
          </button>
          <button
            type="button"
            className="text-xs font-medium text-slate-600 hover:underline"
            onClick={() => setSelectedIds(new Set())}
          >
            Clear selection
          </button>
          <span className="text-xs text-slate-500">{selectedIds.size} selected</span>
          <button
            type="button"
            disabled={bulkBusy || selectedIds.size === 0}
            onClick={() => handleBulk('verified')}
            className="rounded-md border border-green-300 px-2.5 py-1 text-xs font-medium text-green-700 hover:bg-green-50 disabled:opacity-50"
          >
            Verify selected
          </button>
          <button
            type="button"
            disabled={bulkBusy || selectedIds.size === 0}
            onClick={() => handleBulk('rejected')}
            className="rounded-md border border-red-300 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            Reject selected
          </button>
        </div>
      )}

      {bulkMessage && (
        <p className="mt-2 text-sm text-amber-800" role="status">
          {bulkMessage}
        </p>
      )}

      {facts.status === 'loading' && <LoadingBlock label="Loading facts…" />}
      {facts.status === 'error' && <ErrorBlock message={facts.message} onRetry={facts.reload} />}
      {facts.status === 'success' && facts.data.length === 0 && (
        <EmptyBlock message="No facts match these filters yet." />
      )}
      {facts.status === 'success' && facts.data.length > 0 && (
        <div className="mt-3 space-y-5">
          {FACT_TYPE_ORDER.filter((type) => groupedFacts.has(type)).map((type) => (
            <div key={type}>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {FACT_TYPE_LABEL[type]} ({groupedFacts.get(type)?.length})
              </h4>
              <ul className="mt-2 space-y-2">
                {groupedFacts.get(type)!.map((fact) => (
                  <FactCard
                    key={fact.id}
                    fact={fact}
                    selected={selectedIds.has(fact.id)}
                    onToggle={() => toggleSelected(fact.id)}
                    onChanged={facts.reload}
                  />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
