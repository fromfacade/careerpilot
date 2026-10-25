import { useState } from 'react'
import { api } from '../api/client'
import type { EmploymentType, LocationPreferenceType, Preferences, RoleCategory } from '../api/types'
import { useFetch } from '../hooks/useFetch'
import { ErrorBlock, LoadingBlock } from './StatusViews'

const EMPLOYMENT_TYPES: EmploymentType[] = ['internship', 'new_grad', 'full_time', 'contract', 'unknown']
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
const LOCATION_TYPES: LocationPreferenceType[] = ['state', 'metro', 'remote']

function toForm(prefs: Preferences | undefined): Preferences {
  return (
    prefs ?? {
      remote_ok: true,
      target_employment_types: ['internship'],
      target_start_window_start: null,
      target_start_window_end: null,
      min_match_score_to_surface: 0,
      locations: [],
      roles: [],
    }
  )
}

export function PreferencesPanel({ onChanged }: { onChanged: () => void }) {
  // Preferences require a candidate profile to exist (backend returns 404
  // otherwise), so check that first rather than showing a raw API error to
  // a brand-new user.
  const candidate = useFetch(() => api.getCandidate())
  const hasCandidate = candidate.status === 'success' && candidate.data !== null

  // Skip the request entirely until we know a candidate exists — the
  // backend correctly 404s otherwise, but there is no reason to fire a
  // request we already know will fail.
  const prefs = useFetch(
    () => (hasCandidate ? api.getPreferences() : Promise.resolve<Preferences | null>(null)),
    [hasCandidate],
  )
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState<Preferences>(() => toForm(undefined))

  function startEdit() {
    if (prefs.status === 'success' && prefs.data) setForm(prefs.data)
    setEditing(true)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.updatePreferences(form)
      setEditing(false)
      prefs.reload()
      onChanged()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to save preferences')
    } finally {
      setSaving(false)
    }
  }

  function toggleEmploymentType(type: EmploymentType) {
    setForm((f) => ({
      ...f,
      target_employment_types: f.target_employment_types.includes(type)
        ? f.target_employment_types.filter((t) => t !== type)
        : [...f.target_employment_types, type],
    }))
  }

  return (
    <section aria-labelledby="prefs-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <h2 id="prefs-heading" className="text-lg font-semibold text-slate-900">
          Preferences
        </h2>
        {hasCandidate && prefs.status === 'success' && !editing && (
          <button
            type="button"
            onClick={startEdit}
            className="rounded-md border border-slate-300 px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Edit
          </button>
        )}
      </div>

      {candidate.status === 'loading' && <LoadingBlock label="Loading…" />}
      {!hasCandidate && candidate.status === 'success' && (
        <p className="mt-2 text-sm text-slate-500">
          Create a candidate profile above before setting job search preferences.
        </p>
      )}

      {hasCandidate && prefs.status === 'loading' && <LoadingBlock label="Loading preferences…" />}
      {hasCandidate && prefs.status === 'error' && <ErrorBlock message={prefs.message} onRetry={prefs.reload} />}

      {hasCandidate && prefs.status === 'success' && prefs.data && !editing && (
        <dl className="mt-2 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-slate-500">Remote OK</dt>
            <dd className="font-medium text-slate-900">{prefs.data.remote_ok ? 'Yes' : 'No'}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Employment types</dt>
            <dd className="font-medium text-slate-900">
              {prefs.data.target_employment_types.join(', ') || 'none set'}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Start window</dt>
            <dd className="font-medium text-slate-900">
              {prefs.data.target_start_window_start ?? 'unknown'} – {prefs.data.target_start_window_end ?? 'unknown'}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Min match score to surface</dt>
            <dd className="font-medium text-slate-900">{prefs.data.min_match_score_to_surface}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Locations</dt>
            <dd className="font-medium text-slate-900">
              {prefs.data.locations.length
                ? prefs.data.locations.map((l) => `${l.label} (${l.location_type})`).join(', ')
                : 'none set'}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Role priorities</dt>
            <dd className="font-medium text-slate-900">
              {prefs.data.roles.length
                ? prefs.data.roles
                    .slice()
                    .sort((a, b) => a.priority - b.priority)
                    .map((r) => r.role_category)
                    .join(', ')
                : 'none set'}
            </dd>
          </div>
        </dl>
      )}

      {editing && (
        <form onSubmit={handleSubmit} className="mt-3 space-y-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.remote_ok}
              onChange={(e) => setForm({ ...form, remote_ok: e.target.checked })}
            />
            Open to remote roles
          </label>

          <fieldset>
            <legend className="text-sm font-medium text-slate-700">Employment types</legend>
            <div className="mt-1 flex flex-wrap gap-3">
              {EMPLOYMENT_TYPES.map((type) => (
                <label key={type} className="flex items-center gap-1.5 text-sm">
                  <input
                    type="checkbox"
                    checked={form.target_employment_types.includes(type)}
                    onChange={() => toggleEmploymentType(type)}
                  />
                  {type.replace(/_/g, ' ')}
                </label>
              ))}
            </div>
          </fieldset>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="font-medium text-slate-700">Target start — from</span>
              <input
                type="date"
                value={form.target_start_window_start ?? ''}
                onChange={(e) => setForm({ ...form, target_start_window_start: e.target.value || null })}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5"
              />
            </label>
            <label className="block text-sm">
              <span className="font-medium text-slate-700">Target start — to</span>
              <input
                type="date"
                value={form.target_start_window_end ?? ''}
                onChange={(e) => setForm({ ...form, target_start_window_end: e.target.value || null })}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5"
              />
            </label>
          </div>

          <label className="block text-sm">
            <span className="font-medium text-slate-700">
              Minimum match score to surface ({form.min_match_score_to_surface})
            </span>
            <input
              type="range"
              min={0}
              max={100}
              value={form.min_match_score_to_surface}
              onChange={(e) => setForm({ ...form, min_match_score_to_surface: Number(e.target.value) })}
              className="mt-1 block w-full"
            />
          </label>

          <fieldset>
            <legend className="text-sm font-medium text-slate-700">Locations</legend>
            <div className="mt-2 space-y-2">
              {form.locations.map((loc, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <input
                    aria-label={`Location label ${idx + 1}`}
                    value={loc.label}
                    placeholder="e.g. California"
                    onChange={(e) => {
                      const locations = [...form.locations]
                      locations[idx] = { ...loc, label: e.target.value }
                      setForm({ ...form, locations })
                    }}
                    className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-sm"
                  />
                  <select
                    aria-label={`Location type ${idx + 1}`}
                    value={loc.location_type}
                    onChange={(e) => {
                      const locations = [...form.locations]
                      locations[idx] = { ...loc, location_type: e.target.value as LocationPreferenceType }
                      setForm({ ...form, locations })
                    }}
                    className="rounded-md border border-slate-300 px-2 py-1 text-sm"
                  >
                    {LOCATION_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    aria-label={`Remove location ${idx + 1}`}
                    onClick={() => setForm({ ...form, locations: form.locations.filter((_, i) => i !== idx) })}
                    className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
                  >
                    Remove
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={() =>
                  setForm((f) => ({
                    ...f,
                    locations: [...f.locations, { label: '', location_type: 'state', priority: f.locations.length }],
                  }))
                }
                className="rounded-md border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-50"
              >
                + Add location
              </button>
            </div>
          </fieldset>

          <fieldset>
            <legend className="text-sm font-medium text-slate-700">Role priorities (in order)</legend>
            <div className="mt-2 space-y-2">
              {form.roles.map((role, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <select
                    aria-label={`Role priority ${idx + 1}`}
                    value={role.role_category}
                    onChange={(e) => {
                      const roles = [...form.roles]
                      roles[idx] = { ...role, role_category: e.target.value as RoleCategory }
                      setForm({ ...form, roles })
                    }}
                    className="flex-1 rounded-md border border-slate-300 px-2 py-1 text-sm"
                  >
                    {ROLE_CATEGORIES.map((rc) => (
                      <option key={rc} value={rc}>
                        {rc.replace(/_/g, ' ')}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    aria-label={`Remove role priority ${idx + 1}`}
                    onClick={() => setForm({ ...form, roles: form.roles.filter((_, i) => i !== idx) })}
                    className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
                  >
                    Remove
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={() =>
                  setForm((f) => ({ ...f, roles: [...f.roles, { role_category: 'swe_backend', priority: f.roles.length }] }))
                }
                className="rounded-md border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-50"
              >
                + Add role
              </button>
            </div>
          </fieldset>

          <div className="flex gap-2">
            <button
              type="submit"
              disabled={saving}
              className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  )
}
