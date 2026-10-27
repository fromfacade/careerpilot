import { useState } from 'react'
import { api } from '../api/client'
import type { ApplicationPreparation, AutofillAnswerField, AutofillPlanField, AutofillSession } from '../api/types'
import localToken from 'virtual:careerpilot-token'

export function AutofillReview({ prep }: { prep: ApplicationPreparation }) {
  const [session, setSession] = useState<AutofillSession | null>(null)
  const [included, setIncluded] = useState<Record<string, boolean>>({})
  const [overwrite, setOverwrite] = useState<Record<string, boolean>>({})
  const [attachResume, setAttachResume] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const publicUrl = prep.snapshot_apply_url || ''
  const formUrl = prep.greenhouse_apply_url || (publicUrl.includes('greenhouse.io') ? publicUrl : '')
  const note = prep.greenhouse_autofill_note || ''

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

  async function stop() {
    if (!session) return
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
        {formUrl && (
          <button
            type="button"
            disabled={busy}
            onClick={openSession}
            className="rounded-md bg-blue-600 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
          >
            Apply with CareerPilot
          </button>
        )}
        {session && session.state !== 'cancelled' && session.state !== 'failed' && (
          <button type="button" disabled={busy} onClick={stop} className="rounded-md border border-slate-300 px-2 py-1 text-xs">
            Stop
          </button>
        )}
      </div>
      <p className="mt-1 text-xs text-slate-500">
        Opens a visible browser, fills only the fields you approve, and leaves the Greenhouse page for you to submit.
      </p>
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
          {plan && (
            <>
              <p>
                Resume: {plan.resume.display_name || 'None'} ({plan.resume.kind}). {plan.resume.reason}
              </p>
              {plan.resume.eligible_for_attach && (
                <label className="flex items-center gap-2 text-xs">
                  <input type="checkbox" checked={attachResume} onChange={(event) => setAttachResume(event.target.checked)} />
                  Attach this resume
                </label>
              )}
              <FieldChoices
                title="Proposed fields"
                fields={plan.ready.map((field) => ({
                  id: field.field_id,
                  label: field.label,
                  value: field.proposed_value,
                  source: field.source_kind,
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
              <PlainList title="Missing information" rows={[...plan.missing_required.map((field) => field.label), ...plan.answers.missing.map((field) => field.label), ...plan.clarification.map((field) => field.uncertainty || field.label)]} />
              <PlainList title="Sensitive questions" rows={[...plan.sensitive.map((field) => field.label), ...plan.answers.sensitive.map((field) => field.label)]} />
              <PlainList title="Unsupported fields" rows={plan.unsupported.map((field) => field.label || field.semantic)} />
            </>
          )}
          {['ready_to_fill', 'filled_for_review', 'needs_review'].includes(session.state) && (
            <button type="button" disabled={busy} onClick={fill} className="rounded-md bg-slate-900 px-2 py-1 text-xs font-medium text-white disabled:opacity-50">
              Fill approved fields
            </button>
          )}
          {session.result && (
            <div>
              <p className="font-medium text-slate-900">After filling</p>
              <p className="text-xs">Resume: {session.result.resume_status}. {session.result.resume_detail}</p>
              <p className="text-xs">Submitted by CareerPilot: {session.result.submitted ? 'yes' : 'no'}</p>
              <PlainList title="Filled" rows={session.result.outcomes.filter((item) => item.status === 'filled').map((item) => item.label)} />
              <PlainList title="Failed" rows={session.result.outcomes.filter((item) => item.status === 'failed' || item.status === 'stale').map((item) => `${item.label}: ${item.detail}`)} />
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
  fields: { id: string; label: string; value: string | null; source: string | null }[]
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
        label: field.label,
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

function PlainList({ title, rows }: { title: string; rows: string[] }) {
  const visible = rows.filter(Boolean)
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
