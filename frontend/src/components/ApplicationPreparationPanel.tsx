import { useState } from 'react'
import { api } from '../api/client'
import type { ApplicationPreparation, PreparationAnswer } from '../api/types'
import { useFetch } from '../hooks/useFetch'
import { resumeBullets, resumeHeading, resumeSubline } from '../preparation/resumePreview'
import { AutofillReview } from './AutofillReview'
import { Badge } from './Badge'
import { EmptyBlock, ErrorBlock, LoadingBlock } from './StatusViews'

function items(value: unknown): { text: string; reason?: string }[] {
  return Array.isArray(value) ? (value as { text: string; reason?: string }[]) : []
}

function ResumeFields({
  section,
  detail,
  onBulletIncludedChange,
}: {
  section: string
  detail: Record<string, unknown>
  onBulletIncludedChange?: (bulletIndex: number, included: boolean) => void
}) {
  const subline = resumeSubline(section, detail)
  const bullets = resumeBullets(detail)
  const includedIndexes = Array.isArray(detail.included_bullet_indexes)
    ? (detail.included_bullet_indexes as number[])
    : bullets.map((_, index) => index)
  return (
    <div className="mt-1 space-y-1 text-sm text-slate-700">
      {subline ? <p className="text-slate-500">{subline}</p> : null}
      {bullets.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-5">
          {bullets.map((bullet, index) => {
            const included = includedIndexes.includes(index)
            return (
              <li key={`${index}-${bullet}`} className={included ? '' : 'opacity-50'}>
                {onBulletIncludedChange ? (
                  <label className="flex items-start gap-2">
                    <input
                      type="checkbox"
                      checked={included}
                      onChange={(event) => onBulletIncludedChange(index, event.target.checked)}
                      className="mt-0.5"
                    />
                    <span>{bullet}</span>
                  </label>
                ) : (
                  bullet
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function FactList({
  title,
  section,
  rows,
  onTitleChange,
  onIncludedChange,
  onBulletIncludedChange,
}: {
  title: string
  section: string
  rows?: { title: string; detail: unknown; included?: boolean; selection_reason?: string }[]
  onTitleChange?: (index: number, title: string) => void
  onIncludedChange?: (index: number, included: boolean) => void
  onBulletIncludedChange?: (index: number, bulletIndex: number, included: boolean) => void
}) {
  if (!rows?.length) return null
  return (
    <div>
      <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-800">{title}</h4>
      <ul className="mt-1 space-y-2 text-sm text-slate-700">
        {rows.map((row, index) => {
          const detail = typeof row.detail === 'object' && row.detail ? (row.detail as Record<string, unknown>) : {}
          const heading = resumeHeading(section, row.title, detail)
          const included = row.included !== false
          return (
            <li key={`${title}-${index}`} className={included ? '' : 'opacity-60'}>
              <div className="flex items-start gap-2">
                {onIncludedChange ? (
                  <input
                    type="checkbox"
                    checked={included}
                    onChange={(event) => onIncludedChange(index, event.target.checked)}
                    className="mt-1"
                    aria-label={`Include ${heading || row.title} in export`}
                  />
                ) : null}
                <div className="min-w-0 flex-1">
                  {onTitleChange ? (
                    <input
                      value={row.title}
                      onChange={(event) => onTitleChange(index, event.target.value)}
                      className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm font-medium"
                      aria-label={`${title} heading`}
                    />
                  ) : (
                    <span className="font-medium">{heading}</span>
                  )}
                  {row.selection_reason ? <p className="text-xs text-slate-500">{row.selection_reason}</p> : null}
                  <ResumeFields
                    section={section}
                    detail={detail}
                    onBulletIncludedChange={
                      onBulletIncludedChange ? (bulletIndex, included) => onBulletIncludedChange(index, bulletIndex, included) : undefined
                    }
                  />
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export function ApplicationPreparationPanel({
  selectedId,
  onSelected,
  creating = false,
}: {
  selectedId: number | null
  onSelected: (id: number | null) => void
  creating?: boolean
}) {
  const list = useFetch(() => api.listPreparations(), [selectedId])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const selected =
    list.status === 'success' ? list.data.find((row) => row.id === selectedId) ?? list.data[0] ?? null : null

  async function run(action: () => Promise<unknown>, ok?: string) {
    setBusy(true)
    setMessage(null)
    try {
      const result = await action()
      if (ok) setMessage(ok)
      list.reload()
      return result
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby="prep-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="prep-heading" className="text-lg font-semibold text-slate-900">
        Application preparation
      </h2>
      <p className="mt-1 text-sm text-slate-500">
        Job-specific resumes and answers for review. CareerPilot does not submit applications from
        this screen.
      </p>
      {creating && (
        <p className="mt-2 text-sm text-slate-700" role="status">
          Preparing application materials. This does not submit anything.
        </p>
      )}
      {message && (
        <p className="mt-2 text-sm text-slate-700" role="status">
          {message}
        </p>
      )}
      {list.status === 'loading' && <LoadingBlock label="Loading preparations…" />}
      {list.status === 'error' && <ErrorBlock message={list.message} onRetry={list.reload} />}
      {list.status === 'success' && list.data.length === 0 && (
        <EmptyBlock message="No preparations yet. Use Prepare application on a job card." />
      )}
      {list.status === 'success' && list.data.length > 0 && (
        <div className="mt-3 grid gap-3 lg:grid-cols-[16rem_1fr]">
          <ul className="space-y-2">
            {list.data.map((row) => (
              <li key={row.id}>
                <button
                  type="button"
                  onClick={() => onSelected(row.id)}
                  className={`w-full rounded-md border px-2 py-2 text-left text-sm ${
                    selected?.id === row.id ? 'border-blue-600 bg-blue-50' : 'border-slate-200'
                  }`}
                >
                  <span className="font-medium text-slate-900">{row.snapshot_job_title}</span>
                  <span className="mt-1 block text-xs text-slate-500">{row.snapshot_employer}</span>
                  <Badge tone={row.state === 'ready' ? 'green' : row.state === 'failed' ? 'red' : 'amber'}>
                    {row.state.replace('_', ' ')}
                  </Badge>
                </button>
              </li>
            ))}
          </ul>
          {selected && <PreparationDetail prep={selected} busy={busy} run={run} />}
        </div>
      )}
    </section>
  )
}

function PreparationDetail({
  prep,
  busy,
  run,
}: {
  prep: ApplicationPreparation
  busy: boolean
  run: (action: () => Promise<unknown>, ok?: string) => Promise<unknown>
}) {
  const matched = items(prep.match_report.matched)
  const missing = items(prep.match_report.missing)
  const uncertain = items(prep.match_report.uncertain)

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-base font-semibold text-slate-900">
          {prep.snapshot_job_title} · {prep.snapshot_employer}
        </h3>
        <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{prep.analysis.summary}</p>
        <div className="mt-3 rounded-md border border-slate-200 p-3">
          <p className="text-sm font-semibold text-slate-900">
            Selected resume: {prep.selected_resume_name || 'None'}
          </p>
          <p className="mt-1 text-xs text-slate-600">
            <span className="font-medium">Why selected: </span>
            {prep.resume_selection_reason || 'No approved resume was available for automatic selection.'}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <ResumeOverride prep={prep} busy={busy} run={run} />
            {prep.source_resume_id && (
              <button type="button" disabled={busy} onClick={() => run(() => api.downloadPreparationDocument(prep.id, 'selected'))} className="rounded-md border border-slate-300 px-2 py-1 text-xs">
                Download resume
              </button>
            )}
            <button type="button" disabled={busy} onClick={() => run(() => api.tailorPreparation(prep.id), 'Generated an optional tailored draft.')} className="rounded-md border border-slate-300 px-2 py-1 text-xs">
              Tailor resume for this job
            </button>
            {prep.has_tailored_resume && (
              <button type="button" disabled={busy} onClick={() => run(() => api.revertPreparationTailoring(prep.id), 'Reverted to the selected original resume.')} className="rounded-md border border-slate-300 px-2 py-1 text-xs">
                Revert tailored draft
              </button>
            )}
          </div>
        </div>
        {prep.has_tailored_resume && prep.design_limitation && <p className="mt-2 text-xs text-amber-800">{prep.design_limitation}</p>}
        <AutofillReview prep={prep} />
        {prep.error_message && <p className="mt-1 text-xs text-red-700">{prep.error_message}</p>}
        <details className="mt-2">
          <summary className="cursor-pointer text-xs font-medium text-blue-700">Original job description</summary>
          <p className="mt-1 whitespace-pre-wrap text-xs text-slate-600">{prep.snapshot_description || 'No description was available when this preparation was created.'}</p>
        </details>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <AnalysisColumn title="Required qualifications" rows={prep.analysis.required} />
        <AnalysisColumn title="Preferred qualifications" rows={prep.analysis.preferred} />
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <MatchColumn title="Matched" rows={matched} tone="green" />
        <MatchColumn title="Missing" rows={missing} tone="red" />
        <MatchColumn title="Unknown" rows={uncertain} tone="amber" />
      </div>
      <div className="rounded-md border border-slate-200 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="text-sm font-semibold text-slate-800">Tailored resume</h4>
          <Badge>{prep.tailored_resume_status}</Badge>
        </div>
        {prep.has_tailored_resume ? <TailoredResumeEditor prep={prep} busy={busy} run={run} /> : (
          <p className="mt-2 text-xs text-slate-500">No tailored draft. The selected original file is used unless you tailor for this job.</p>
        )}
        <div className="mt-2 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy || (prep.has_tailored_resume && prep.tailored_resume.quality?.ok === false)}
            onClick={() => run(() => api.updatePreparationResume(prep.id, { status: 'approved' }))}
            className="rounded-md border border-green-300 px-2 py-1 text-xs text-green-700 disabled:opacity-50"
          >
            Approve resume
          </button>
          <button type="button" disabled={busy} onClick={() => run(() => api.updatePreparationResume(prep.id, { status: 'rejected' }))} className="rounded-md border border-red-300 px-2 py-1 text-xs text-red-700">
            Reject resume
          </button>
          {prep.has_docx && (
            <button type="button" disabled={busy} onClick={() => run(() => api.downloadPreparationDocument(prep.id, 'docx'))} className="rounded-md border border-slate-300 px-2 py-1 text-xs">
              Download DOCX
            </button>
          )}
          {prep.has_pdf && (
            <button type="button" disabled={busy} onClick={() => run(() => api.downloadPreparationDocument(prep.id, 'pdf'))} className="rounded-md border border-slate-300 px-2 py-1 text-xs">
              Download PDF
            </button>
          )}
          {prep.source_resume_id && (
            <button type="button" disabled={busy} onClick={() => run(() => api.downloadPreparationDocument(prep.id, 'original'))} className="rounded-md border border-slate-300 px-2 py-1 text-xs">
              Download original
            </button>
          )}
        </div>
      </div>
      <div className="space-y-2">
        <h4 className="text-sm font-semibold text-slate-800">Application answers</h4>
        {prep.answers.map((answer) => (
          <AnswerCard key={`${answer.id}-${answer.updated_at}`} prepId={prep.id} answer={answer} busy={busy} run={run} />
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled={busy} onClick={() => run(() => api.regeneratePreparation(prep.id), 'Regenerated drafts.')} className="rounded-md border border-slate-300 px-2 py-1 text-xs">
          Regenerate drafts
        </button>
        <button type="button" disabled={busy} onClick={() => run(() => api.cancelPreparation(prep.id), 'Cancelled this preparation.')} className="rounded-md border border-red-300 px-2 py-1 text-xs text-red-700">
          Cancel preparation
        </button>
      </div>
    </div>
  )
}

function ResumeOverride({
  prep,
  busy,
  run,
}: {
  prep: ApplicationPreparation
  busy: boolean
  run: (action: () => Promise<unknown>, ok?: string) => Promise<unknown>
}) {
  const resumes = useFetch(() => api.listResumes(), [])
  const options = resumes.status === 'success' ? resumes.data.filter((row) => row.is_approved && !row.is_archived) : []
  if (options.length === 0) return null
  return (
    <label className="inline-flex items-center gap-1 text-xs text-slate-700">
      Change resume
      <select
        disabled={busy}
        value={prep.source_resume_id ?? ''}
        onChange={(event) => run(() => api.selectPreparationResume(prep.id, Number(event.target.value)), 'Updated the selected resume.')}
        className="rounded-md border border-slate-300 px-2 py-1 text-xs"
      >
        {options.map((row) => (
          <option key={row.id} value={row.id}>
            {row.profile_name || row.original_filename}
          </option>
        ))}
      </select>
    </label>
  )
}

function AnalysisColumn({
  title,
  rows,
}: {
  title: string
  rows?: { text: string; evidence?: string }[]
}) {
  return (
    <div className="rounded-md border border-slate-200 p-2">
      <p className="text-xs font-semibold text-slate-500">{title}</p>
      {!rows?.length && <p className="mt-1 text-xs text-slate-500">None extracted</p>}
      <ul className="mt-1 space-y-1">
        {(rows ?? []).map((row) => (
          <li key={row.text} className="text-xs text-slate-700">
            {row.text}
            {row.evidence ? <span className="block text-slate-500">{row.evidence}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

function TailoredResumeEditor({
  prep,
  busy,
  run,
}: {
  prep: ApplicationPreparation
  busy: boolean
  run: (action: () => Promise<unknown>, ok?: string) => Promise<unknown>
}) {
  const [draft, setDraft] = useState(prep.tailored_resume)
  const quality = prep.tailored_resume.quality
  const header = draft.header ?? {}
  const contact = [header.email, header.phone, header.location, header.linkedin_url, header.github_url]
    .filter(Boolean)
    .join(' | ')

  function updateTitle(section: 'education' | 'work_experience' | 'projects' | 'skills' | 'achievements', index: number, title: string) {
    setDraft((current) => ({
      ...current,
      [section]: (current[section] ?? []).map((row, rowIndex) => (rowIndex === index ? { ...row, title } : row)),
    }))
  }

  function updateIncluded(section: 'education' | 'work_experience' | 'projects' | 'skills' | 'achievements', index: number, included: boolean) {
    setDraft((current) => ({
      ...current,
      [section]: (current[section] ?? []).map((row, rowIndex) => (rowIndex === index ? { ...row, included } : row)),
    }))
  }

  function updateBulletIncluded(
    section: 'work_experience' | 'projects',
    index: number,
    bulletIndex: number,
    included: boolean,
  ) {
    setDraft((current) => ({
      ...current,
      [section]: (current[section] ?? []).map((row, rowIndex) => {
        if (rowIndex !== index) return row
        const detail = typeof row.detail === 'object' && row.detail ? { ...(row.detail as Record<string, unknown>) } : {}
        const bullets = Array.isArray(detail.bullets) ? (detail.bullets as unknown[]) : []
        const currentIndexes = Array.isArray(detail.included_bullet_indexes)
          ? [...(detail.included_bullet_indexes as number[])]
          : bullets.map((_, itemIndex) => itemIndex)
        const next = included
          ? Array.from(new Set([...currentIndexes, bulletIndex])).sort((left, right) => left - right)
          : currentIndexes.filter((item) => item !== bulletIndex)
        return { ...row, detail: { ...detail, included_bullet_indexes: next } }
      }),
    }))
  }

  return (
    <div className="mt-2 space-y-3">
      {quality?.ok === false && (
        <div className="rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-800" role="alert">
          <p className="font-semibold">This export is not ready.</p>
          <ul className="mt-1 list-disc pl-4">
            {(quality.issues ?? []).map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </div>
      )}
      {quality?.warnings?.length ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
          {quality.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      ) : null}
      {draft.presentation?.note ? <p className="text-xs text-slate-500">{draft.presentation.note}</p> : null}
      {draft.presentation?.two_page_reason ? (
        <p className="text-xs text-amber-900">{draft.presentation.two_page_reason}</p>
      ) : null}
      {draft.presentation?.tradeoff ? <p className="text-xs text-amber-900">{draft.presentation.tradeoff}</p> : null}
      <div className="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
        <p className="text-center text-lg font-semibold text-slate-900">{header.full_name}</p>
        {contact ? <p className="mt-1 text-center text-xs text-slate-600">{contact}</p> : null}
        <div className="mt-3 space-y-3">
          <FactList title="Education" section="education" rows={draft.education} onTitleChange={(index, title) => updateTitle('education', index, title)} onIncludedChange={(index, included) => updateIncluded('education', index, included)} />
          <FactList title="Experience" section="work_experience" rows={draft.work_experience} onTitleChange={(index, title) => updateTitle('work_experience', index, title)} onIncludedChange={(index, included) => updateIncluded('work_experience', index, included)} onBulletIncludedChange={(index, bulletIndex, included) => updateBulletIncluded('work_experience', index, bulletIndex, included)} />
          <FactList title="Projects" section="projects" rows={draft.projects} onTitleChange={(index, title) => updateTitle('projects', index, title)} onIncludedChange={(index, included) => updateIncluded('projects', index, included)} onBulletIncludedChange={(index, bulletIndex, included) => updateBulletIncluded('projects', index, bulletIndex, included)} />
          <FactList title="Skills" section="skills" rows={draft.skills} onTitleChange={(index, title) => updateTitle('skills', index, title)} onIncludedChange={(index, included) => updateIncluded('skills', index, included)} />
          <FactList title="Achievements" section="achievements" rows={draft.achievements} onTitleChange={(index, title) => updateTitle('achievements', index, title)} onIncludedChange={(index, included) => updateIncluded('achievements', index, included)} />
        </div>
      </div>
      {prep.has_pdf && (
        <iframe
          title="Tailored resume PDF preview"
          src={api.preparationPdfPreviewUrl(prep.id)}
          className="h-[720px] w-full rounded-md border border-slate-200 bg-slate-50"
        />
      )}
      <button
        type="button"
        disabled={busy}
        onClick={() => run(() => api.updatePreparationResume(prep.id, { tailored_resume: draft }), 'Saved resume wording.')}
        className="rounded-md border border-slate-300 px-2 py-1 text-xs"
      >
        Save resume edits
      </button>
    </div>
  )
}

function MatchColumn({
  title,
  rows,
  tone,
}: {
  title: string
  rows: { text: string; reason?: string }[]
  tone: 'green' | 'red' | 'amber'
}) {
  return (
    <div className="rounded-md border border-slate-200 p-2">
      <p className="text-xs font-semibold text-slate-500">{title}</p>
      {rows.length === 0 && <p className="mt-1 text-xs text-slate-500">None</p>}
      <ul className="mt-1 space-y-1">
        {rows.map((row) => (
          <li key={row.text} className="text-xs text-slate-700">
            <Badge tone={tone}>{title}</Badge> {row.text}
            {row.reason ? <span className="block text-slate-500">{row.reason}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

function AnswerCard({
  prepId,
  answer,
  busy,
  run,
}: {
  prepId: number
  answer: PreparationAnswer
  busy: boolean
  run: (action: () => Promise<unknown>, ok?: string) => Promise<unknown>
}) {
  const [text, setText] = useState(answer.answer_text)
  return (
    <article className="rounded-md border border-slate-200 p-3">
      <div className="flex flex-wrap gap-2">
        <Badge tone={answer.origin === 'reused' ? 'green' : 'amber'}>{answer.origin}</Badge>
        <Badge>{answer.status}</Badge>
        {answer.is_sensitive && <Badge tone="amber">Sensitive</Badge>}
      </div>
      <h5 className="mt-1 text-sm font-semibold text-slate-900">{answer.question}</h5>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
      />
      {answer.unsupported_claims.length > 0 && (
        <p className="mt-1 text-xs text-amber-800">Unsupported: {answer.unsupported_claims.map(String).join(' ')}</p>
      )}
      {answer.missing_information.length > 0 && (
        <p className="mt-1 text-xs text-amber-800">Missing: {answer.missing_information.map(String).join(' ')}</p>
      )}
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" disabled={busy} onClick={() => run(() => api.updatePreparationAnswer(prepId, answer.id, { answer_text: text }))} className="rounded-md border border-slate-300 px-2 py-1 text-xs">
          Save edit
        </button>
        <button
          type="button"
          disabled={busy || Boolean(answer.missing_information.length && !text.trim())}
          onClick={() => run(() => api.updatePreparationAnswer(prepId, answer.id, { status: 'approved', answer_text: text }))}
          className="rounded-md border border-green-300 px-2 py-1 text-xs text-green-700 disabled:opacity-50"
        >
          Approve
        </button>
        <button type="button" disabled={busy} onClick={() => run(() => api.updatePreparationAnswer(prepId, answer.id, { status: 'rejected' }))} className="rounded-md border border-red-300 px-2 py-1 text-xs text-red-700">
          Reject
        </button>
      </div>
    </article>
  )
}
