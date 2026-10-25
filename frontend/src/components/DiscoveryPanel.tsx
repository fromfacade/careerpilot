import { useState } from 'react'
import { api } from '../api/client'
import { useFetch } from '../hooks/useFetch'
import { Badge } from './Badge'
import { ErrorBlock, LoadingBlock } from './StatusViews'

const RUN_STATUS_TONE: Record<string, 'green' | 'red' | 'amber' | 'slate'> = {
  succeeded: 'green',
  failed: 'red',
  partial: 'amber',
  running: 'slate',
  pending: 'slate',
}

export function DiscoveryPanel({ onRunCompleted }: { onRunCompleted: () => void }) {
  const latest = useFetch(() => api.getLatestDiscoveryRun())
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleTrigger() {
    setRunning(true)
    setError(null)
    try {
      await api.triggerDiscoveryRun()
      latest.reload()
      onRunCompleted()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Discovery run failed to start')
    } finally {
      setRunning(false)
    }
  }

  return (
    <section aria-labelledby="discovery-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="discovery-heading" className="text-lg font-semibold text-slate-900">
          Discovery
        </h2>
        <button
          type="button"
          onClick={handleTrigger}
          disabled={running}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {running ? 'Running…' : 'Run discovery now'}
        </button>
      </div>

      {error && <ErrorBlock message={error} />}

      {latest.status === 'loading' && <LoadingBlock label="Loading latest run…" />}
      {latest.status === 'error' && <ErrorBlock message={latest.message} onRetry={latest.reload} />}
      {latest.status === 'success' && latest.data === null && (
        <p className="mt-2 text-sm text-slate-500">No discovery runs yet. Add a job source, then run discovery.</p>
      )}
      {latest.status === 'success' && latest.data && (
        <div className="mt-2 text-sm">
          <p>
            Latest run: <Badge tone={RUN_STATUS_TONE[latest.data.status]}>{latest.data.status}</Badge>{' '}
            <span className="text-slate-500">
              ({new Date(latest.data.started_at).toLocaleString()}, trigger: {latest.data.trigger_type})
            </span>
          </p>
          <p className="mt-1 text-slate-600">
            Sources: {latest.data.sources_succeeded}/{latest.data.sources_attempted} succeeded &middot; Jobs created{' '}
            {latest.data.jobs_created}, updated {latest.data.jobs_updated}, deactivated {latest.data.jobs_deactivated}
          </p>
          {latest.data.error_summary && <p className="mt-1 text-red-700">{latest.data.error_summary}</p>}
          {latest.data.sources.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-slate-600">
              {latest.data.sources.map((s) => (
                <li key={s.job_source_id}>
                  {s.employer_name} ({s.provider}): <Badge tone={RUN_STATUS_TONE[s.status] ?? 'slate'}>{s.status}</Badge>{' '}
                  {s.jobs_found} found, {s.jobs_created} new
                  {s.error_message ? ` — ${s.error_message}` : ''}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
