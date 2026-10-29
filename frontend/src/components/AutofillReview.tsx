import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ApplicationPreparation, AutofillAnswerField, AutofillPlanField, AutofillSession, CompletionMetrics } from '../api/types'
import localToken from 'virtual:careerpilot-token'
import { beginAutofillOpening, releaseAutofillOpening } from './autofillOpening'

export function AutofillReview({
  prep,
  onApplicationStatus,
  autoStart = false,
  hideLauncher = false,
}: {
  prep: ApplicationPreparation
  onApplicationStatus?: (status: string) => void
  autoStart?: boolean
  hideLauncher?: boolean
}) {
  const [session, setSession] = useState<AutofillSession | null>(null)
  const [included, setIncluded] = useState<Record<string, boolean>>({})
  const [overwrite, setOverwrite] = useState<Record<string, boolean>>({})
  const [attachResume, setAttachResume] = useState(true)
  const [busy, setBusy] = useState(autoStart)
  const [error, setError] = useState<string | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [draftText, setDraftText] = useState<Record<string, string>>({})
  const publicUrl = prep.snapshot_apply_url || ''
  const formUrl = prep.greenhouse_apply_url || (publicUrl.includes('greenhouse.io') ? publicUrl : '')
  const note = prep.greenhouse_autofill_note || ''

  function approvedIds(next: AutofillSession) {
    const ready = next.plan?.ready.map((field) => field.field_id) ?? []
    const answers = next.plan?.answers.matched.filter((field) => field.approval_status === 'approved').map((field) => field.field_id) ?? []
    return [...ready, ...answers]
  }

  async function openSession() {
    setBusy(true)
    setError(null)
    try {
      const next = await api.openAutofillSession(prep.id)
      setSession(next)
      const choices: Record<string, boolean> = {}
      next.plan?.ready.forEach((field) => {
        choices[field.field_id] = true
      })
      next.plan?.answers.matched.forEach((field) => {
        choices[field.field_id] = true
      })
      setIncluded(choices)
      setAttachResume(Boolean(next.plan?.resume.eligible_for_attach))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The browser could not be opened.')
    } finally {
      setBusy(false)
    }
  }

  function draftValue(field: AutofillAnswerField) {
    return draftText[field.field_id] ?? field.proposed_text ?? ''
  }

  async function saveDraft(field: AutofillAnswerField, status: 'draft' | 'approved' | 'rejected') {
    if (!session || field.source_id == null) return
    setBusy(true)
    setError(null)
    try {
      const text = draftValue(field)
      await api.updatePreparationAnswer(prep.id, field.source_id, {
        ...(text === (field.proposed_text ?? '') ? {} : { answer_text: text }),
        status,
      })
      const refreshed = await api.refreshAutofillSession(session.id)
      if (status !== 'approved') {
        setSession(refreshed)
        return
      }
      const filled = await api.fillAutofillSession(session.id, {
        included_field_ids: [field.field_id],
        overwrite_field_ids: [],
        attach_resume: false,
      })
      setSession(filled)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The draft could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  async function regenerateDraft(field: AutofillAnswerField) {
    if (!session) return
    setBusy(true)
    setError(null)
    try {
      const next = await api.regenerateAutofillDraft(session.id, field.field_id)
      setDraftText((current) => {
        const copy = { ...current }
        delete copy[field.field_id]
        return copy
      })
      setSession(next)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The draft could not be regenerated.')
    } finally {
      setBusy(false)
    }
  }

  async function fill() {
    if (!session) return
    setBusy(true)
    setError(null)
    try {
      const next = await api.fillAutofillSession(session.id, {
        included_field_ids: Object.entries(included).filter(([, on]) => on).map(([id]) => id),
        overwrite_field_ids: Object.entries(overwrite).filter(([, on]) => on).map(([id]) => id),
        attach_resume: attachResume,
      })
      setSession(next)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The fill could not finish.')
    } finally {
      setBusy(false)
    }
  }

  async function submit() {
    if (!session || !confirmed) return
    setBusy(true)
    setError(null)
    try {
      const next = await api.submitAutofillSession(session.id, {
        confirm: true,
        preparation_id: session.preparation_id,
        apply_url: session.apply_url,
      })
      setSession(next)
      if (next.application_status) onApplicationStatus?.(next.application_status)
      setConfirmed(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The application was not submitted.')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    if (!autoStart || !formUrl) return
    let active = true
    void beginAutofillOpening(prep.id, async (opened) => {
      const included = approvedIds(opened)
      return api.fillAutofillSession(opened.id, {
        included_field_ids: included,
        overwrite_field_ids: [],
        attach_resume: Boolean(opened.plan?.resume.eligible_for_attach),
      })
    })
      .then((filled) => {
        if (!active) return
        setSession(filled)
        if (filled.state === 'failed' || filled.state === 'cancelled') {
          setError(filled.message || 'The browser could not stay open.')
        }
        const choices: Record<string, boolean> = {}
        approvedIds(filled).forEach((id) => {
          choices[id] = true
        })
        setIncluded(choices)
        setAttachResume(Boolean(filled.plan?.resume.eligible_for_attach))
        if (filled.application_status) onApplicationStatus?.(filled.application_status)
      })
      .catch((err: unknown) => {
        if (!active) return
        setError(err instanceof Error ? err.message : 'The application form could not be prepared.')
      })
      .finally(() => {
        if (active) setBusy(false)
      })
    return () => {
      active = false
    }
  }, [autoStart, formUrl, prep.id, onApplicationStatus])

  async function stop() {
    if (!session) return
    releaseAutofillOpening(prep.id)
    setBusy(true)
    try {
      setSession(await api.cancelAutofillSession(session.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The session could not be stopped.')
    } finally {
      setBusy(false)
    }
  }

  if (!formUrl && !note) return null
  const plan = session?.plan

  return (
    <div className="mt-3 rounded-md border border-slate-200 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-semibold text-slate-900">Greenhouse autofill</h4>
        {formUrl && (!hideLauncher || error) && (
          <button
            type="button"
            disabled={busy}
            onClick={openSession}
            className="rounded-md bg-blue-600 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
          >
            {hideLauncher ? 'Try the form again' : 'Apply with CareerPilot'}
          </button>
        )}
        {session && session.state !== 'cancelled' && session.state !== 'failed' && (
          <button type="button" disabled={busy} onClick={stop} className="rounded-md border border-slate-300 px-2 py-1 text-xs">
            Stop
          </button>
        )}
      </div>
      <p className="mt-1 text-xs text-slate-500">
        Opens a visible browser and fills only approved fields. Sending an application requires a separate confirmation for that job.
      </p>
      {autoStart && busy && !session && (
        <p className="mt-2 text-sm text-slate-700">Opening the Greenhouse form and filling approved fields. Nothing is submitted.</p>
      )}
      {publicUrl && <p className="mt-1 break-all text-xs text-slate-500">Posting: {publicUrl}</p>}
      {formUrl && <p className="mt-1 break-all text-xs text-slate-500">Application form: {formUrl}</p>}
      {note && <p className="mt-2 text-sm text-amber-800">{note}</p>}
      {!localToken && (
        <p className="mt-2 text-sm text-amber-800">
          The local API token is not loaded. Start the API, then restart this frontend dev server.
        </p>
      )}
      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
      {session && (
        <div className="mt-3 space-y-3 text-sm text-slate-700">
          <p>
            <span className="font-medium">{session.job_title}</span> · {session.employer}
          </p>
          <p className="break-all text-xs text-slate-500">{session.apply_url}</p>
          <p>
            Browser status: <span className="font-medium">{session.state.replaceAll('_', ' ')}</span>. {session.message}
          </p>
          <p className="text-sm">
            {fillingPaused(plan, session.state)
              ? 'Filling is paused. An active verification challenge is on the page. Complete it in the browser, then choose Fill approved fields again. CareerPilot will not solve it.'
              : canSubmit(session)
                ? 'Filling is permitted for the checked fields. Submission still requires the confirmation below.'
                : 'Filling is permitted for the checked fields. CareerPilot will not submit until this application is ready and you confirm it.'}
          </p>
          {session.readiness && (
            <div className="rounded-md bg-slate-50 p-2 text-xs text-slate-700">
              <p className="font-medium text-slate-900">
                {session.readiness.status === 'ready_to_submit'
                  ? 'Ready for submission. Nothing is sent until you confirm this application below.'
                  : 'Needs review before submission. CareerPilot will not submit.'}
              </p>
              <ul className="mt-1 list-disc pl-4">
                {session.readiness.checks
                  .filter((item) => item.status !== 'passed')
                  .map((item) => (
                    <li key={item.code}>{item.detail}</li>
                  ))}
              </ul>
            </div>
          )}
          {plan && (
            <>
              <p>
                Selected resume: {plan.resume.display_name || 'None'} ({plan.resume.kind}). {plan.resume.reason}
              </p>
              {plan.resume.upload_name && (
                <p className="text-xs text-slate-500">The application will show this file as {plan.resume.upload_name}.</p>
              )}
              {!plan.resume.eligible_for_attach && (
                <p className="text-sm text-amber-800">The selected resume will not be attached. {plan.resume.reason}</p>
              )}
              {plan.resume.eligible_for_attach && (
                <label className="flex items-center gap-2 text-xs">
                  <input type="checkbox" checked={attachResume} onChange={(event) => setAttachResume(event.target.checked)} />
                  Attach this resume
                </label>
              )}
              {session.completion && <CompletionSummary metrics={session.completion} />}
              {completedRows(session).length > 0 && (
                <details className="rounded-md bg-slate-50 p-2">
                  <summary className="cursor-pointer font-medium text-slate-900">Inspect completed fields</summary>
                  <PlainList title="Verified on the form" rows={completedRows(session)} />
                </details>
              )}
              <details className="rounded-md bg-slate-50 p-2">
                <summary className="cursor-pointer font-medium text-slate-900">Approved fields</summary>
                <div className="mt-2 space-y-2">
                  <FieldChoices
                    title="Verified information"
                    fields={plan.ready.map((field) => ({
                      id: field.field_id,
                      label: field.label,
                      value: field.proposed_value,
                      source: field.source_kind,
                      note: field.match_note,
                    }))}
                    included={included}
                    onToggle={(id, on) => setIncluded((current) => ({ ...current, [id]: on }))}
                  />
                  <AnswerChoices
                    title="Approved answers"
                    fields={plan.answers.matched}
                    included={included}
                    onToggle={(id, on) => setIncluded((current) => ({ ...current, [id]: on }))}
                  />
                  <ReplaceChoices
                    fields={[...plan.preserve_existing, ...plan.answers.preserved.map(asPlanField)]}
                    overwrite={overwrite}
                    onToggle={(id, on) => setOverwrite((current) => ({ ...current, [id]: on }))}
                  />
                </div>
              </details>
              <DraftAnswers
                fields={plan.answers.missing.filter(isSavedDraft)}
                textFor={draftValue}
                busy={busy}
                onChange={(id, value) => setDraftText((current) => ({ ...current, [id]: value }))}
                onSave={(field) => saveDraft(field, 'draft')}
                onApprove={(field) => saveDraft(field, 'approved')}
                onReject={(field) => saveDraft(field, 'rejected')}
                onRegenerate={regenerateDraft}
              />
              <PlainList title="Missing candidate data" rows={missingRows(plan)} />
              <PlainList title="Not selected" rows={unmatchedRows(plan)} />
              <PlainList title="Sensitive questions" rows={[...plan.sensitive.map(fieldReason), ...plan.answers.sensitive.map(answerReason)]} />
              <PlainList title="Unsupported form controls" rows={plan.unsupported.filter((field) => !answeredIds(plan).has(field.field_id)).map(fieldReason)} />
            </>
          )}
          {['ready_to_fill', 'filled_for_review', 'needs_review'].includes(session.state) && (
            <button type="button" disabled={busy} onClick={fill} className="rounded-md bg-slate-900 px-2 py-1 text-xs font-medium text-white disabled:opacity-50">
              Fill approved fields
            </button>
          )}
          {canSubmit(session) && (
            <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-950">
              <p className="font-medium">Ready for submission</p>
              <p className="mt-1">Employer: {session.employer}</p>
              <p>Job: {session.job_title}</p>
              <p className="break-all">Application URL: {session.apply_url}</p>
              <p>Selected resume: {plan?.resume.display_name || 'None'}</p>
              <p>Required fields: {checkDetail(session, 'required_fields')}</p>
              <p>Unresolved questions: {unresolvedText(session)}</p>
              <p className="mt-2 font-medium">
                Clicking Submit this application sends it to {session.employer}. CareerPilot cannot undo that.
              </p>
              <label className="mt-2 flex items-start gap-2">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                <span>I confirm this submission for {session.job_title} at {session.employer} only.</span>
              </label>
              <button
                type="button"
                disabled={busy || !confirmed}
                onClick={submit}
                className="mt-2 rounded-md bg-amber-800 px-2 py-1 font-medium text-white disabled:opacity-50"
              >
                Submit this application
              </button>
            </div>
          )}
          {session.application_status && ['submitted', 'submission_failed', 'confirmation_unknown', 'submitting'].includes(session.application_status) && (
            <p className="text-sm font-medium text-slate-900">{submissionLabel(session.application_status)}. {session.message}</p>
          )}
          {session.result && (
            <div>
              <p className="font-medium text-slate-900">After filling</p>
              <p className="text-xs">Resume: {session.result.resume_status}. {session.result.resume_detail}</p>
              <p className="text-xs">Submitted by CareerPilot: {session.result.submitted ? 'yes' : 'no'}</p>
              <PlainList title="Needs another look" rows={session.result.outcomes.filter((item) => item.status === 'failed' || item.status === 'stale').map((item) => `${item.label}: ${item.detail}`)} />
              <PlainList title="Unresolved required fields" rows={session.result.unresolved} />
            </div>
          )}
          <a className="text-xs text-blue-700 underline" href={session.apply_url} target="_blank" rel="noreferrer">
            Inspect the application URL
          </a>
        </div>
      )}
    </div>
  )
}

function completedRows(session: AutofillSession) {
  return (session.result?.outcomes || [])
    .filter((item) => item.status === 'filled' || item.status === 'preserved')
    .map((item) => {
      if (item.status === 'preserved') return `${item.label}: already complete`
      if (item.detail && item.detail !== 'Verified.') return `${item.label}: ${item.detail}`
      return `${item.label}: filled automatically`
    })
}

function CompletionSummary({ metrics }: { metrics: CompletionMetrics }) {
  const done = metrics.autofilled + metrics.already_completed
  return (
    <div className="rounded-md bg-slate-50 p-2 text-xs text-slate-700">
      <p className="font-medium text-slate-900">
        {metrics.total === 0 ? 'No applicable fields were found.' : `${done} of ${metrics.total} fields completed.`}
      </p>
      <p className="mt-1">
        {metrics.autofilled} filled automatically. {metrics.already_completed} already complete. {metrics.manual} need attention.{' '}
        {metrics.required_unanswered} required still unanswered. {metrics.percent}% complete.
      </p>
    </div>
  )
}

function answeredIds(plan: NonNullable<AutofillSession['plan']>) {
  return new Set(
    [
      ...plan.answers.matched,
      ...plan.answers.missing,
      ...plan.answers.ambiguous,
      ...plan.answers.sensitive,
      ...plan.answers.preserved,
    ].map((field) => field.field_id),
  )
}

function canSubmit(session: AutofillSession) {
  const blocked = ['submitting', 'submitted', 'submission_failed', 'confirmation_unknown']
  return (
    session.readiness?.status === 'ready_to_submit' &&
    !blocked.includes(session.application_status || '') &&
    ['ready_to_fill', 'filled_for_review', 'needs_review'].includes(session.state)
  )
}

function checkDetail(session: AutofillSession, code: string) {
  return session.readiness?.checks.find((item) => item.code === code)?.detail || 'Not checked.'
}

function unresolvedText(session: AutofillSession) {
  const open = session.readiness?.checks.filter((item) => item.status !== 'passed').map((item) => item.detail) || []
  return open.length ? open.join(' ') : 'None.'
}

function submissionLabel(status: string) {
  const labels: Record<string, string> = {
    submitting: 'Submitting',
    submitted: 'Successfully submitted',
    submission_failed: 'Submission failed',
    confirmation_unknown: 'Confirmation unknown',
  }
  return labels[status] || status
}

function asPlanField(field: AutofillAnswerField): AutofillPlanField {
  return {
    field_id: field.field_id,
    label: field.label,
    semantic: 'custom_question',
    proposed_value: field.proposed_text,
    proposed_replacement: field.proposed_replacement,
    existing_value: field.existing_value,
    required: field.required,
    uncertainty: field.uncertainty,
    source_kind: field.source,
  }
}

function FieldChoices({
  title,
  fields,
  included,
  onToggle,
}: {
  title: string
  fields: { id: string; label: string; value: string | null; source: string | null; note?: string }[]
  included: Record<string, boolean>
  onToggle: (id: string, on: boolean) => void
}) {
  if (fields.length === 0) return null
  return (
    <div>
      <p className="font-medium text-slate-900">{title}</p>
      <ul className="mt-1 space-y-1">
        {fields.map((field) => (
          <li key={field.id}>
            <label className="flex items-start gap-2">
              <input type="checkbox" checked={included[field.id] !== false} onChange={(event) => onToggle(field.id, event.target.checked)} />
              <span>
                {field.label}: {field.value}
                {field.source ? <span className="text-xs text-slate-500"> ({field.source})</span> : null}
                {field.note ? <span className="block text-xs text-slate-500">{field.note}</span> : null}
              </span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  )
}

function AnswerChoices({
  title,
  fields,
  included,
  onToggle,
}: {
  title: string
  fields: AutofillAnswerField[]
  included: Record<string, boolean>
  onToggle: (id: string, on: boolean) => void
}) {
  return (
    <FieldChoices
      title={title}
      fields={fields.map((field) => ({
        id: field.field_id,
        label: answerHeading(field),
        value: field.proposed_text,
        source: field.approval_status,
      }))}
      included={included}
      onToggle={onToggle}
    />
  )
}

function ReplaceChoices({
  fields,
  overwrite,
  onToggle,
}: {
  fields: AutofillPlanField[]
  overwrite: Record<string, boolean>
  onToggle: (id: string, on: boolean) => void
}) {
  const rows = fields.filter((field) => field.proposed_replacement)
  if (rows.length === 0) return null
  return (
    <div>
      <p className="font-medium text-slate-900">Existing values</p>
      <ul className="mt-1 space-y-1">
        {rows.map((field) => (
          <li key={field.field_id}>
            <label className="flex items-start gap-2">
              <input type="checkbox" checked={Boolean(overwrite[field.field_id])} onChange={(event) => onToggle(field.field_id, event.target.checked)} />
              <span>
                Keep the current {field.label} value unless you approve replacing it with {field.proposed_replacement}.
              </span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  )
}

function fieldReason(field: AutofillPlanField): string {
  return `${field.label}: ${field.uncertainty || 'This field was not filled.'}`
}

function answerHeading(field: AutofillAnswerField): string {
  const permission =
    field.eligible_for_fill === true ? 'Autofill permitted.' : field.eligible_for_fill === false ? 'Manual review required.' : ''
  return [field.label, matchLabel(field.match_kind), field.explanation || '', permission].filter(Boolean).join(' ')
}

function matchLabel(kind: string | undefined): string {
  const labels: Record<string, string> = {
    exact_match: 'Exact match.',
    equivalent_match: 'Equivalent match.',
    uncertain_match: 'Uncertain match.',
    no_match: 'No match.',
  }
  return kind ? labels[kind] || '' : ''
}

function answerReason(field: AutofillAnswerField): string {
  const reason = field.explanation || field.uncertainty || 'No approved answer was entered.'
  const permission =
    field.eligible_for_fill === true ? 'Autofill permitted.' : field.review_required ? 'Manual review required.' : ''
  return `${field.label}: ${matchLabel(field.match_kind)} ${reason} ${permission}`.replace(/\s+/g, ' ').trim()
}

function isSavedDraft(field: AutofillAnswerField) {
  return (
    field.source_id != null &&
    (field.approval_status === 'draft' || field.approval_status === 'needs_review' || field.approval_status === 'rejected')
  )
}

function missingRows(plan: NonNullable<AutofillSession['plan']>): string[] {
  return [
    ...plan.missing_required.map(fieldReason),
    ...plan.answers.missing.filter((field) => !isSavedDraft(field)).map(answerReason),
    ...plan.clarification.filter((field) => isMissing(field.uncertainty)).map(fieldReason),
  ]
}

function DraftAnswers({
  fields,
  textFor,
  busy,
  onChange,
  onSave,
  onApprove,
  onReject,
  onRegenerate,
}: {
  fields: AutofillAnswerField[]
  textFor: (field: AutofillAnswerField) => string
  busy: boolean
  onChange: (id: string, value: string) => void
  onSave: (field: AutofillAnswerField) => void
  onApprove: (field: AutofillAnswerField) => void
  onReject: (field: AutofillAnswerField) => void
  onRegenerate: (field: AutofillAnswerField) => void
}) {
  if (fields.length === 0) return null
  return (
    <div>
      <p className="font-medium text-slate-900">Draft answers</p>
      <ul className="mt-1 space-y-3">
        {fields.map((field) => {
          const text = textFor(field)
          const factual = (field.uncertainty || '').includes('will not guess')
          return (
            <li key={field.field_id} className="rounded-md border border-slate-200 p-2">
              <p className="font-medium text-slate-900">{field.label}</p>
              <p className="text-xs text-slate-600">{field.explanation || field.uncertainty}</p>
              {(field.supporting_facts || []).length > 0 && (
                <p className="text-xs text-slate-600">Supported by verified facts: {field.supporting_facts?.join(', ')}</p>
              )}
              <textarea
                aria-label={`Draft for ${field.label}`}
                value={text}
                onChange={(event) => onChange(field.field_id, event.target.value)}
                className="mt-1 w-full rounded-md border border-slate-300 p-1 text-xs"
                rows={4}
              />
              <p className="text-xs text-slate-500">{text.length} characters. This draft is not filled until you approve it.</p>
              <div className="mt-1 flex flex-wrap gap-1">
                <button type="button" disabled={busy} onClick={() => onSave(field)} className="rounded-md border border-slate-300 px-2 py-1 text-xs">
                  Save {field.label}
                </button>
                <button
                  type="button"
                  disabled={busy || !text.trim()}
                  onClick={() => onApprove(field)}
                  className="rounded-md bg-slate-900 px-2 py-1 text-xs text-white disabled:opacity-50"
                >
                  Approve {field.label}
                </button>
                <button type="button" disabled={busy} onClick={() => onReject(field)} className="rounded-md border border-slate-300 px-2 py-1 text-xs">
                  Reject {field.label}
                </button>
                {!factual && (
                  <button type="button" disabled={busy} onClick={() => onRegenerate(field)} className="rounded-md border border-slate-300 px-2 py-1 text-xs">
                    Regenerate {field.label}
                  </button>
                )}
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function unmatchedRows(plan: NonNullable<AutofillSession['plan']>): string[] {
  return [
    ...plan.clarification.filter((field) => !isMissing(field.uncertainty)).map(fieldReason),
    ...plan.answers.ambiguous.map(answerReason),
  ]
}

function isMissing(uncertainty: string | null): boolean {
  const text = uncertainty || ''
  return text.includes('No verified') || text.includes('not a single city') || text.includes('degree level alone')
}

function fillingPaused(plan: AutofillSession['plan'] | undefined, state: string): boolean {
  const blockers = plan?.blockers ?? []
  return state === 'needs_review' && blockers.some((item) => item === 'captcha' || item === 'mfa')
}

function PlainList({ title, rows }: { title: string; rows: string[] }) {
  const visible = [...new Set(rows.filter(Boolean))]
  if (visible.length === 0) return null
  return (
    <div>
      <p className="font-medium text-slate-900">{title}</p>
      <ul className="mt-1 list-disc pl-5 text-xs">
        {visible.map((row) => (
          <li key={row}>{row}</li>
        ))}
      </ul>
    </div>
  )
}
