import { useState } from 'react'
import { api } from '../api/client'
import type { TriState, WorkAuthStatus } from '../api/types'
import { useFetch } from '../hooks/useFetch'
import { ErrorBlock, LoadingBlock } from './StatusViews'

const WORK_AUTH_OPTIONS: { value: WorkAuthStatus; label: string }[] = [
  { value: 'unknown', label: 'Unknown / prefer not to say yet' },
  { value: 'us_citizen', label: 'U.S. citizen' },
  { value: 'permanent_resident', label: 'Permanent resident' },
  { value: 'visa_holder', label: 'Visa holder' },
  { value: 'requires_sponsorship', label: 'Requires future sponsorship' },
]

const TRI_STATE_OPTIONS: { value: TriState; label: string }[] = [
  { value: 'unknown', label: 'Unknown' },
  { value: 'yes', label: 'Yes' },
  { value: 'no', label: 'No' },
]

export function ProfilePanel({ onChanged }: { onChanged: () => void }) {
  const candidate = useFetch(() => api.getCandidate())
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    phone: '',
    current_location: '',
    country: '',
    school: '',
    graduation_date: '',
    work_authorization_status: 'unknown' as WorkAuthStatus,
    requires_sponsorship: 'unknown' as TriState,
  })

  function startEdit() {
    if (candidate.status === 'success' && candidate.data) {
      const c = candidate.data
      setForm({
        full_name: c.full_name,
        email: c.email,
        phone: c.phone ?? '',
        current_location: c.current_location ?? '',
        country: c.country ?? '',
        school: c.school ?? '',
        graduation_date: c.graduation_date ?? '',
        work_authorization_status: c.work_authorization_status,
        requires_sponsorship: c.requires_sponsorship,
      })
    }
    setEditing(true)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      const exists = candidate.status === 'success' && candidate.data !== null
      const payload = {
        full_name: form.full_name,
        email: form.email,
        phone: form.phone || null,
        current_location: form.current_location || null,
        country: form.country || null,
        school: form.school || null,
        graduation_date: form.graduation_date || null,
        graduation_date_precision: form.graduation_date ? ('month' as const) : ('unknown' as const),
        work_authorization_status: form.work_authorization_status,
        requires_sponsorship: form.requires_sponsorship,
      }
      if (exists) {
        await api.updateCandidate(payload)
      } else {
        await api.createCandidate(payload)
      }
      setEditing(false)
      candidate.reload()
      onChanged()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to save profile')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section aria-labelledby="profile-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <h2 id="profile-heading" className="text-lg font-semibold text-slate-900">
          Candidate profile
        </h2>
        {candidate.status === 'success' && !editing && (
          <button
            type="button"
            onClick={startEdit}
            className="rounded-md border border-slate-300 px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            {candidate.data ? 'Edit' : 'Create profile'}
          </button>
        )}
      </div>

      {candidate.status === 'loading' && <LoadingBlock label="Loading profile…" />}
      {candidate.status === 'error' && <ErrorBlock message={candidate.message} onRetry={candidate.reload} />}

      {candidate.status === 'success' && !editing && candidate.data === null && (
        <p className="mt-2 text-sm text-slate-500">
          No profile yet. Create one so eligibility and match scoring can run for discovered jobs.
        </p>
      )}

      {candidate.status === 'success' && !editing && candidate.data && (
        <dl className="mt-2 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-slate-500">Name</dt>
            <dd className="font-medium text-slate-900">{candidate.data.full_name}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Email</dt>
            <dd className="font-medium text-slate-900">{candidate.data.email}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Phone</dt>
            <dd className="font-medium text-slate-900">{candidate.data.phone ?? 'Not set'}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Location</dt>
            <dd className="font-medium text-slate-900">{candidate.data.current_location ?? 'Not set'}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Country</dt>
            <dd className="font-medium text-slate-900">{candidate.data.country ?? 'Not set'}</dd>
          </div>
          <div>
            <dt className="text-slate-500">School</dt>
            <dd className="font-medium text-slate-900">{candidate.data.school ?? 'unknown'}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Graduation date</dt>
            <dd className="font-medium text-slate-900">{candidate.data.graduation_date ?? 'unknown'}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Work authorization</dt>
            <dd className="font-medium text-slate-900">{candidate.data.work_authorization_status}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Requires sponsorship</dt>
            <dd className="font-medium text-slate-900">{candidate.data.requires_sponsorship}</dd>
          </div>
        </dl>
      )}

      {editing && (
        <form onSubmit={handleSubmit} className="mt-3 space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="font-medium text-slate-700">Full name</span>
              <input
                required
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5"
              />
            </label>
            <label className="block text-sm">
              <span className="font-medium text-slate-700">Email</span>
              <input
                required
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5"
              />
            </label>
            <label className="block text-sm">
              <span className="font-medium text-slate-700">Phone</span>
              <input
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5"
              />
            </label>
            <label className="block text-sm">
              <span className="font-medium text-slate-700">Location (city)</span>
              <input
                value={form.current_location}
                onChange={(e) => setForm({ ...form, current_location: e.target.value })}
                placeholder="Austin, TX"
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5"
              />
            </label>
            <label className="block text-sm">
              <span className="font-medium text-slate-700">Country</span>
              <input
                value={form.country}
                onChange={(e) => setForm({ ...form, country: e.target.value })}
                placeholder="United States"
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5"
              />
            </label>
            <label className="block text-sm">
              <span className="font-medium text-slate-700">School</span>
              <input
                value={form.school}
                onChange={(e) => setForm({ ...form, school: e.target.value })}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5"
              />
            </label>
            <label className="block text-sm">
              <span className="font-medium text-slate-700">Graduation date</span>
              <input
                type="date"
                value={form.graduation_date}
                onChange={(e) => setForm({ ...form, graduation_date: e.target.value })}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5"
              />
            </label>
            <label className="block text-sm">
              <span className="font-medium text-slate-700">Work authorization</span>
              <select
                value={form.work_authorization_status}
                onChange={(e) => setForm({ ...form, work_authorization_status: e.target.value as WorkAuthStatus })}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5"
              >
                {WORK_AUTH_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="font-medium text-slate-700">Requires future sponsorship?</span>
              <select
                value={form.requires_sponsorship}
                onChange={(e) => setForm({ ...form, requires_sponsorship: e.target.value as TriState })}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5"
              >
                {TRI_STATE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
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
