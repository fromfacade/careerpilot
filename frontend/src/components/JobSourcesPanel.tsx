import { useState } from 'react'
import { api } from '../api/client'
import type { JobProvider } from '../api/types'
import { useFetch } from '../hooks/useFetch'
import { Badge } from './Badge'
import { ErrorBlock, LoadingBlock } from './StatusViews'

const STATUS_TONE: Record<string, 'green' | 'red' | 'amber' | 'slate'> = {
  never_run: 'slate',
  success: 'green',
  partial: 'amber',
  failure: 'red',
}

export function JobSourcesPanel() {
  const sources = useFetch(() => api.listJobSources())
  const [form, setForm] = useState({ employer_name: '', provider: 'greenhouse' as JobProvider, board_token: '' })
  const [submitting, setSubmitting] = useState(false)

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    try {
      await api.createJobSource(form)
      setForm({ employer_name: '', provider: 'greenhouse', board_token: '' })
      sources.reload()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to add job source')
    } finally {
      setSubmitting(false)
    }
  }

  async function toggleEnabled(id: number, isEnabled: boolean) {
    await api.updateJobSource(id, { is_enabled: !isEnabled })
    sources.reload()
  }

  return (
    <section aria-labelledby="sources-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="sources-heading" className="text-lg font-semibold text-slate-900">
        Job source registry
      </h2>
      <p className="mt-1 text-sm text-slate-500">
        Each row is one employer's board on Greenhouse, Lever, or Ashby. Public APIs only expose jobs per employer
        board, so add the boards you care about here.
      </p>

      {sources.status === 'loading' && <LoadingBlock label="Loading job sources…" />}
      {sources.status === 'error' && <ErrorBlock message={sources.message} onRetry={sources.reload} />}
      {sources.status === 'success' && (
        <ul className="mt-3 space-y-2">
          {sources.data.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-slate-100 p-2 text-sm">
              <span>
                <span className="font-medium">{s.employer_name}</span> &middot; {s.provider}/{s.board_token}
              </span>
              <span className="flex items-center gap-2">
                <Badge tone={STATUS_TONE[s.last_fetch_status]}>{s.last_fetch_status}</Badge>
                {s.last_fetch_error && (
                  <span className="max-w-xs truncate text-xs text-red-700" title={s.last_fetch_error}>
                    {s.last_fetch_error}
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => toggleEnabled(s.id, s.is_enabled)}
                  className="rounded-md border border-slate-300 px-2 py-0.5 text-xs font-medium hover:bg-slate-50"
                >
                  {s.is_enabled ? 'Disable' : 'Enable'}
                </button>
              </span>
            </li>
          ))}
          {sources.data.length === 0 && <li className="text-sm text-slate-500">No job sources configured yet.</li>}
        </ul>
      )}

      <form onSubmit={handleAdd} className="mt-4 flex flex-wrap items-end gap-2 border-t border-slate-100 pt-3">
        <label className="text-sm">
          <span className="block font-medium text-slate-700">Employer name</span>
          <input
            required
            value={form.employer_name}
            onChange={(e) => setForm({ ...form, employer_name: e.target.value })}
            className="mt-1 rounded-md border border-slate-300 px-2 py-1"
            placeholder="Acme Corp"
          />
        </label>
        <label className="text-sm">
          <span className="block font-medium text-slate-700">Provider</span>
          <select
            value={form.provider}
            onChange={(e) => setForm({ ...form, provider: e.target.value as JobProvider })}
            className="mt-1 rounded-md border border-slate-300 px-2 py-1"
          >
            <option value="greenhouse">Greenhouse</option>
            <option value="lever">Lever</option>
            <option value="ashby">Ashby</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="block font-medium text-slate-700">Board token</span>
          <input
            required
            value={form.board_token}
            onChange={(e) => setForm({ ...form, board_token: e.target.value })}
            className="mt-1 rounded-md border border-slate-300 px-2 py-1"
            placeholder="acme"
          />
        </label>
        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Add source
        </button>
      </form>
    </section>
  )
}
