import { useState } from 'react'
import { api } from '../api/client'
import type { JobState } from '../api/types'
import { useFetch } from '../hooks/useFetch'
import { JobCard } from './JobCard'
import { ErrorBlock, LoadingBlock } from './StatusViews'

const FILTERS: { value: JobState | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'new', label: 'New' },
  { value: 'saved', label: 'Saved' },
  { value: 'dismissed', label: 'Dismissed' },
]

export function JobsSection({ refreshSignal }: { refreshSignal: number }) {
  const [filter, setFilter] = useState<JobState | 'all'>('all')
  const [busyJobId, setBusyJobId] = useState<number | null>(null)

  const jobs = useFetch(
    () => api.listJobs(filter === 'all' ? undefined : { state: filter }),
    [filter, refreshSignal],
  )

  async function updateState(jobId: number, state: JobState) {
    setBusyJobId(jobId)
    try {
      await api.setJobState(jobId, state)
      jobs.reload()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update job state')
    } finally {
      setBusyJobId(null)
    }
  }

  return (
    <section aria-labelledby="jobs-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="jobs-heading" className="text-lg font-semibold text-slate-900">
          Jobs
        </h2>
        <div role="group" aria-label="Filter jobs by state" className="flex gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setFilter(f.value)}
              aria-pressed={filter === f.value}
              className={`rounded-md px-3 py-1 text-sm font-medium ${
                filter === f.value
                  ? 'bg-blue-600 text-white'
                  : 'border border-slate-300 text-slate-700 hover:bg-slate-50'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-3">
        {jobs.status === 'loading' && <LoadingBlock label="Loading jobs…" />}
        {jobs.status === 'error' && <ErrorBlock message={jobs.message} onRetry={jobs.reload} />}
        {jobs.status === 'success' && jobs.data.length === 0 && (
          <p className="text-sm text-slate-500">
            No jobs match this filter yet. Add a job source and run discovery to pull real listings.
          </p>
        )}
        {jobs.status === 'success' && jobs.data.length > 0 && (
          <ul className="space-y-3">
            {jobs.data.map((job) => (
              <JobCard
                key={job.id}
                job={job}
                busy={busyJobId === job.id}
                onSave={() => updateState(job.id, 'saved')}
                onDismiss={() => updateState(job.id, 'dismissed')}
                onUnsave={() => updateState(job.id, 'new')}
              />
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
