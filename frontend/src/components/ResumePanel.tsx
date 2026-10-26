import { useRef, useState } from 'react'
import { api } from '../api/client'
import type { CandidateFact, FactType, FactVerificationStatus, Resume, ResumeUploadResult } from '../api/types'
import { useFetch } from '../hooks/useFetch'
import { Badge } from './Badge'
import { EmptyBlock, ErrorBlock, LoadingBlock } from './StatusViews'

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

// Deliberately a distinct mapping from job eligibility/relevance badges
// (see JobCard.tsx) -- this is a human-review state, not a computed
// verdict. 'unverified' is always the starting state for every extracted
// fact; it is never silently assumed to be correct.
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

/** Read-only rendering of `fact_value`, whose shape varies by `fact_type`
 * (see docs/data-model.md §2a and app/resume_parsing/section_parser.py) --
 * never assumes one fixed shape, falls back to raw JSON for anything
 * unrecognized rather than silently showing nothing. */
function FactValueView({ fact }: { fact: CandidateFact }) {
  const v = fact.fact_value as {
    bullets?: string[]
    dates_text?: string | null
    items?: string[]
    text?: string
  }

  if (Array.isArray(v.bullets)) {
    return (
      <div className="mt-1 text-sm text-slate-700">
        {v.dates_text && <p className="text-xs font-medium text-slate-500">{v.dates_text}</p>}
        {v.bullets.length > 0 ? (
          <ul className="mt-1 list-inside list-disc space-y-0.5">
            {v.bullets.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        ) : (
          <p className="text-slate-500">No bullet points detected.</p>
        )}
      </div>
    )
  }

  if (Array.isArray(v.items)) {
    return (
      <div className="mt-1 flex flex-wrap gap-1">
        {v.items.map((item, i) => (
          <Badge key={i} tone="slate">
            {item}
          </Badge>
        ))}
      </div>
    )
  }

  if (typeof v.text === 'string') {
    return <p className="mt-1 text-sm text-slate-700">{v.text}</p>
  }

  return <pre className="mt-1 whitespace-pre-wrap text-xs text-slate-500">{JSON.stringify(fact.fact_value)}</pre>
}

/** Converts a fact's structured value into a single editable text block,
 * and back. Only the field that's actually present for this fact's shape
 * is edited -- `dates_text`/`raw_block` (when present) are preserved
 * untouched so an edit never silently discards other extracted detail. */
function factValueToEditText(fact: CandidateFact): string {
  const v = fact.fact_value as { bullets?: string[]; items?: string[]; text?: string }
  if (Array.isArray(v.bullets)) return v.bullets.join('\n')
  if (Array.isArray(v.items)) return v.items.join(', ')
  if (typeof v.text === 'string') return v.text
  return JSON.stringify(fact.fact_value, null, 2)
}

function editTextToFactValue(fact: CandidateFact, text: string): Record<string, unknown> {
  const v = fact.fact_value as Record<string, unknown>
  if (Array.isArray(v.bullets)) {
    return { ...v, bullets: text.split('\n').map((s) => s.trim()).filter(Boolean) }
  }
  if (Array.isArray(v.items)) {
    return { ...v, items: text.split(',').map((s) => s.trim()).filter(Boolean) }
  }
  if (typeof v.text === 'string') {
    return { ...v, text }
  }
  // Unrecognized shape: require valid JSON back rather than silently
  // discarding structure we don't understand.
  return JSON.parse(text) as Record<string, unknown>
}

function FactCard({ fact, onChanged }: { fact: CandidateFact; onChanged: () => void }) {
  const [editing, setEditing] = useState(false)
  const [editKey, setEditKey] = useState(fact.fact_key)
  const [editText, setEditText] = useState('')
  const [busy, setBusy] = useState(false)

  function startEdit() {
    setEditKey(fact.fact_key)
    setEditText(factValueToEditText(fact))
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
    let fact_value: Record<string, unknown>
    try {
      fact_value = editTextToFactValue(fact, editText)
    } catch {
      alert('Could not parse that edit back into a valid value (expected JSON for this fact).')
      return
    }
    await run(async () => {
      await api.updateCandidateFact(fact.id, { fact_key: editKey, fact_value })
      setEditing(false)
    })
  }

  return (
    <li className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <Badge tone="blue">{FACT_TYPE_LABEL[fact.fact_type]}</Badge>
            <Badge tone={VERIFICATION_TONE[fact.verification_status]}>{fact.verification_status}</Badge>
          </div>
          {!editing && <h4 className="mt-1 text-sm font-semibold text-slate-900">{fact.fact_key}</h4>}
        </div>
      </div>

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
          <label className="block text-xs">
            <span className="font-medium text-slate-700">Content</span>
            <textarea
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              rows={4}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
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
              Verify
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={startEdit}
              className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              Edit
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
      resumes.reload()
      facts.reload()
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  return (
    <section aria-labelledby="resume-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="resume-heading" className="text-lg font-semibold text-slate-900">
        Resume &amp; verified facts
      </h2>
      <p className="mt-1 text-sm text-slate-500">
        Upload a PDF or DOCX resume. Education, skills, projects, work experience, and achievements are extracted
        deterministically (no AI, no network calls) and stored below as facts awaiting your review — nothing is
        assumed verified until you say so. Uploaded files are kept immutable and are never committed to source
        control.
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
          Uploaded <span className="font-medium">{lastUpload.resume.original_filename}</span> —{' '}
          {lastUpload.resume.parse_status === 'success' && `${lastUpload.facts_extracted} fact(s) extracted.`}
          {lastUpload.resume.parse_status === 'partial' &&
            `${lastUpload.facts_extracted} fact(s) extracted, but some content didn't match a recognized resume section.`}
          {lastUpload.resume.parse_status === 'failed' &&
            `the file was saved, but parsing failed: ${lastUpload.resume.parse_error}`}
        </p>
      )}

      <h3 className="mt-4 text-sm font-semibold text-slate-900">Uploaded resumes</h3>
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
                <span className="font-medium">{r.original_filename}</span> ({r.file_format.toUpperCase()}) &middot;
                uploaded {formatDate(r.created_at)}
              </span>
              <span className="flex items-center gap-2">
                <Badge tone={PARSE_STATUS_TONE[r.parse_status]}>{r.parse_status}</Badge>
                {r.parse_error && (
                  <span className="max-w-xs truncate text-xs text-red-700" title={r.parse_error}>
                    {r.parse_error}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-5 flex flex-wrap items-end justify-between gap-2 border-t border-slate-100 pt-4">
        <h3 className="text-sm font-semibold text-slate-900">Extracted facts</h3>
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

      {facts.status === 'loading' && <LoadingBlock label="Loading facts…" />}
      {facts.status === 'error' && <ErrorBlock message={facts.message} onRetry={facts.reload} />}
      {facts.status === 'success' && facts.data.length === 0 && (
        <EmptyBlock message="No facts match these filters yet." />
      )}
      {facts.status === 'success' && facts.data.length > 0 && (
        <ul className="mt-2 space-y-2">
          {facts.data.map((fact) => (
            <FactCard key={fact.id} fact={fact} onChanged={facts.reload} />
          ))}
        </ul>
      )}
    </section>
  )
}
