import { useState } from 'react'
import { api } from '../api/client'
import type { AutoApplySettings, AutoApplyUpdate, EmploymentType, Resume, RoleCategory } from '../api/types'
import { useFetch } from '../hooks/useFetch'
import { ErrorBlock, LoadingBlock } from './StatusViews'

const EMPLOYMENT_TYPES: EmploymentType[] = ['internship', 'new_grad', 'full_time', 'contract']
const ROLE_CATEGORIES: RoleCategory[] = [
  'swe_backend',
  'swe_frontend',
  'swe_fullstack',
  'infrastructure',
  'ai_engineering',
  'cybersecurity',
  'qa',
  'it_support',
  'other',
]

type FormState = {
  enabled: boolean
  acknowledge: boolean
  job_categories: RoleCategory[]
  employment_types: EmploymentType[]
  locations: string[]
  location_draft: string
  min_match_score: number
  max_per_day: number
  max_per_session: number
  resume_ids: number[]
  expires_at: string
}

function toLocalInput(iso: string | null): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function toForm(settings: AutoApplySettings): FormState {
  return {
    enabled: settings.enabled,
    acknowledge: false,
    job_categories: settings.job_categories,
    employment_types: settings.employment_types,
    locations: settings.locations,
    location_draft: '',
    min_match_score: settings.min_match_score,
    max_per_day: settings.max_per_day,
    max_per_session: settings.max_per_session,
    resume_ids: settings.resumes.map((resume) => resume.id),
    expires_at: toLocalInput(settings.expires_at),
  }
}

function toPayload(form: FormState): AutoApplyUpdate {
  const expires = form.expires_at ? new Date(form.expires_at).toISOString() : null
  return {
    enabled: form.enabled,
    acknowledge: form.acknowledge,
    provider: 'greenhouse',
    job_categories: form.job_categories,
    employment_types: form.employment_types,
    locations: form.locations,
    min_match_score: form.min_match_score,
    max_per_day: form.max_per_day,
    max_per_session: form.max_per_session,
    resume_ids: form.resume_ids,
    expires_at: expires,
  }
}

export function AutoApplyPanel() {
  const candidate = useFetch(() => api.getCandidate())
  const hasCandidate = candidate.status === 'success' && candidate.data !== null
  const settings = useFetch(
    () => (hasCandidate ? api.getAutoApply() : Promise.resolve<AutoApplySettings | null>(null)),
    [hasCandidate],
  )
  const resumes = useFetch(() => (hasCandidate ? api.listResumes() : Promise.resolve<Resume[] | null>(null)), [
    hasCandidate,
  ])
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState<FormState | null>(null)
  const [error, setError] = useState<string | null>(null)

  function startEdit(current: AutoApplySettings) {
    setForm(toForm(current))
    setError(null)
    setEditing(true)
  }

  async function save(event: React.FormEvent) {
    event.preventDefault()
    if (!form) return
    if (form.enabled && !form.acknowledge) {
      setError('Check the acknowledgement before enabling Auto-Apply.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await api.updateAutoApply(toPayload(form))
      setEditing(false)
      settings.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save Auto-Apply settings')
    } finally {
      setSaving(false)
    }
  }

  async function disable(current: AutoApplySettings) {
    setSaving(true)
    setError(null)
    try {
      await api.updateAutoApply({
        ...toPayload(toForm(current)),
        enabled: false,
        acknowledge: false,
      })
      setEditing(false)
      settings.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not turn off Auto-Apply')
    } finally {
      setSaving(false)
    }
  }

  const approvedResumes =
    resumes.status === 'success' && resumes.data
      ? resumes.data.filter((resume) => resume.is_approved && !resume.is_archived)
      : []

  return (
    <section aria-labelledby="auto-apply-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <h2 id="auto-apply-heading" className="text-lg font-semibold text-slate-900">
          Auto-Apply
        </h2>
        {hasCandidate && settings.status === 'success' && settings.data && !editing && (
          <button
            type="button"
            onClick={() => startEdit(settings.data as AutoApplySettings)}
            className="rounded-md border border-slate-300 px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Edit
          </button>
        )}
      </div>

      {candidate.status === 'loading' && <LoadingBlock label="Loading…" />}
      {!hasCandidate && candidate.status === 'success' && (
        <p className="mt-2 text-sm text-slate-500">Create a candidate profile before configuring Auto-Apply.</p>
      )}
      {hasCandidate && settings.status === 'loading' && <LoadingBlock label="Loading Auto-Apply…" />}
      {hasCandidate && settings.status === 'error' && <ErrorBlock message={settings.message} onRetry={settings.reload} />}

      {hasCandidate && settings.status === 'success' && settings.data && !editing && (
        <AutoApplySummary settings={settings.data} saving={saving} onDisable={() => disable(settings.data as AutoApplySettings)} />
      )}

      {editing && form && (
        <form onSubmit={save} className="mt-3 space-y-4">
          <p className="text-sm text-slate-700">{settings.status === 'success' && settings.data ? settings.data.explanation : ''}</p>
          <p className="text-sm text-slate-500">
            Greenhouse is the only authorized job board. Saving these settings does not submit an application.
          </p>
          <label className="flex items-start gap-2 text-sm text-slate-800">
            <input
              type="checkbox"
              className="mt-1"
              checked={form.acknowledge}
              onChange={(event) => setForm({ ...form, acknowledge: event.target.checked })}
            />
            <span>Auto-Apply allows CareerPilot to submit eligible, complete applications automatically within your configured limits.</span>
          </label>
          <label className="flex items-center gap-2 text-sm font-medium text-slate-800">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
            />
            Enable Auto-Apply
          </label>

          <CheckboxGroup
            legend="Authorized job categories"
            options={ROLE_CATEGORIES}
            selected={form.job_categories}
            onToggle={(value) =>
              setForm({
                ...form,
                job_categories: toggle(form.job_categories, value),
              })
            }
          />
          <CheckboxGroup
            legend="Authorized employment types"
            options={EMPLOYMENT_TYPES}
            selected={form.employment_types}
            onToggle={(value) =>
              setForm({
                ...form,
                employment_types: toggle(form.employment_types, value),
              })
            }
          />

          <fieldset>
            <legend className="text-sm font-medium text-slate-700">Authorized locations</legend>
            <p className="mt-1 text-sm text-slate-500">
              A job matches only when the location text is the same. Add Remote to authorize remote jobs.
            </p>
            <ul className="mt-2 space-y-1 text-sm text-slate-800">
              {form.locations.map((location) => (
                <li key={location} className="flex items-center justify-between gap-2">
                  <span>{location}</span>
                  <button
                    type="button"
                    className="text-slate-500 hover:text-slate-800"
                    onClick={() => setForm({ ...form, locations: form.locations.filter((item) => item !== location) })}
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
            <div className="mt-2 flex gap-2">
              <input
                aria-label="Location to authorize"
                value={form.location_draft}
                placeholder="Santa Cruz, CA"
                onChange={(event) => setForm({ ...form, location_draft: event.target.value })}
                className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-sm"
              />
              <button
                type="button"
                className="rounded-md border border-slate-300 px-3 py-1 text-sm"
                onClick={() => {
                  const label = form.location_draft.trim()
                  if (!label || form.locations.some((item) => item.toLowerCase() === label.toLowerCase())) {
                    setForm({ ...form, location_draft: '' })
                    return
                  }
                  setForm({ ...form, locations: [...form.locations, label], location_draft: '' })
                }}
              >
                Add location
              </button>
            </div>
          </fieldset>

          <label className="block text-sm">
            <span className="font-medium text-slate-700">Minimum match score ({form.min_match_score})</span>
            <input
              type="range"
              min={0}
              max={100}
              value={form.min_match_score}
              onChange={(event) => setForm({ ...form, min_match_score: Number(event.target.value) })}
              className="mt-1 block w-full"
            />
          </label>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <NumberField
              label="Daily application limit"
              value={form.max_per_day}
              onChange={(value) => setForm({ ...form, max_per_day: value })}
            />
            <NumberField
              label="Session application limit"
              value={form.max_per_session}
              onChange={(value) => setForm({ ...form, max_per_session: value })}
            />
          </div>
          <fieldset>
            <legend className="text-sm font-medium text-slate-700">Approved resume profiles</legend>
            <div className="mt-2 space-y-1">
              {approvedResumes.length === 0 && <p className="text-sm text-slate-500">No approved resume profiles yet.</p>}
              {approvedResumes.map((resume) => (
                <label key={resume.id} className="flex items-center gap-2 text-sm text-slate-800">
                  <input
                    type="checkbox"
                    checked={form.resume_ids.includes(resume.id)}
                    onChange={() => setForm({ ...form, resume_ids: toggle(form.resume_ids, resume.id) })}
                  />
                  {resume.profile_name || resume.original_filename}
                </label>
              ))}
            </div>
          </fieldset>
          <label className="block text-sm">
            <span className="font-medium text-slate-700">Authorization expiration</span>
            <input
              type="datetime-local"
              aria-label="Authorization expiration"
              value={form.expires_at}
              onChange={(event) => setForm({ ...form, expires_at: event.target.value })}
              className="mt-1 block rounded-md border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
          {error && (
            <p role="alert" className="text-sm text-red-700">
              {error}
            </p>
          )}
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={saving}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
            >
              Save Auto-Apply
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700"
            >
              Cancel
            </button>
          </div>
        </form>
      )}
      {error && !editing && (
        <p role="alert" className="mt-2 text-sm text-red-700">
          {error}
        </p>
      )}
    </section>
  )
}

function AutoApplySummary({
  settings,
  saving,
  onDisable,
}: {
  settings: AutoApplySettings
  saving: boolean
  onDisable: () => void
}) {
  const expires = settings.expires_at ? new Date(settings.expires_at).toLocaleString() : 'Not set'
  return (
    <div className="mt-3 space-y-3">
      <p className="text-sm text-slate-700">{settings.explanation}</p>
      <p className="text-sm font-medium text-slate-900">
        {settings.active
          ? 'Auto-Apply is active. CareerPilot still asks you to confirm each application before it is sent.'
          : 'Auto-Apply is not active. Review Mode asks you to confirm each job.'}
      </p>
      <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
        <Fact label="Current mode" value={settings.mode === 'auto_apply' ? 'Auto-Apply' : 'Review'} />
        <Fact label="Authorized job categories" value={settings.job_categories.join(', ') || 'None'} />
        <Fact label="Authorized employment types" value={settings.employment_types.join(', ') || 'None'} />
        <Fact label="Authorized locations" value={settings.locations.join(', ') || 'None'} />
        <Fact label="Minimum match score" value={String(settings.min_match_score)} />
        <Fact label="Daily application limit" value={String(settings.max_per_day)} />
        <Fact label="Session application limit" value={String(settings.max_per_session)} />
        <Fact
          label="Approved resume profiles"
          value={settings.resumes.map((resume) => resume.profile_name).join(', ') || 'None'}
        />
        <Fact label="Authorization expiration" value={expires} />
        <Fact label="Authorized job board" value="Greenhouse" />
      </dl>
      {settings.active && (
        <button
          type="button"
          onClick={onDisable}
          disabled={saving}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
        >
          Turn off Auto-Apply
        </button>
      )}
    </div>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-medium text-slate-900">{value}</dd>
    </div>
  )
}

function CheckboxGroup<T extends string>({
  legend,
  options,
  selected,
  onToggle,
}: {
  legend: string
  options: T[]
  selected: T[]
  onToggle: (value: T) => void
}) {
  return (
    <fieldset>
      <legend className="text-sm font-medium text-slate-700">{legend}</legend>
      <div className="mt-2 grid grid-cols-1 gap-1 sm:grid-cols-2">
        {options.map((option) => (
          <label key={option} className="flex items-center gap-2 text-sm text-slate-800">
            <input type="checkbox" checked={selected.includes(option)} onChange={() => onToggle(option)} />
            {option.replaceAll('_', ' ')}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="block text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      <input
        type="number"
        min={0}
        max={25}
        aria-label={label}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-1 block w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
      />
    </label>
  )
}

function toggle<T>(values: T[], value: T): T[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value]
}
