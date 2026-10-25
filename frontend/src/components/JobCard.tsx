import { useState } from 'react'
import type { Job } from '../api/types'
import { Badge } from './Badge'

const ELIGIBILITY_TONE: Record<string, 'green' | 'red' | 'amber'> = {
  eligible: 'green',
  ineligible: 'red',
  unknown: 'amber',
}

function formatDate(value: string | null): string {
  if (!value) return 'unknown'
  try {
    return new Date(value).toLocaleDateString()
  } catch {
    return value
  }
}

export function JobCard({
  job,
  onSave,
  onDismiss,
  onUnsave,
  busy,
}: {
  job: Job
  onSave: () => void
  onDismiss: () => void
  onUnsave: () => void
  busy: boolean
}) {
  const [showReasons, setShowReasons] = useState(false)

  return (
    <li className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-slate-900">{job.title}</h3>
          <p className="text-sm text-slate-600">
            {job.employer_name} &middot; via {job.provider}
          </p>
        </div>
        {job.assessment && (
          <div className="flex flex-col items-end gap-1">
            <Badge tone={ELIGIBILITY_TONE[job.assessment.eligibility]}>
              Eligibility: {job.assessment.eligibility}
            </Badge>
            <span className="text-sm font-semibold text-slate-700">Match: {job.assessment.match_score}/100</span>
          </div>
        )}
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        <Badge>{job.employment_type.replace('_', ' ')}</Badge>
        <Badge>{job.role_category.replace('_', ' ')}</Badge>
        <Badge>{job.remote_type}</Badge>
        {!job.is_active && <Badge tone="amber">no longer listed</Badge>}
      </div>

      <p className="mt-2 text-sm text-slate-600">
        {job.locations.map((l) => l.raw_text).join(', ') || 'Location unspecified'} &middot; posted{' '}
        {formatDate(job.posted_at)}
      </p>

      {job.assessment && (job.assessment.eligibility_reasons.length > 0 || job.assessment.match_reasons.length > 0) && (
        <div className="mt-2">
          <button
            type="button"
            className="text-xs font-medium text-blue-700 underline-offset-2 hover:underline"
            onClick={() => setShowReasons((v) => !v)}
            aria-expanded={showReasons}
          >
            {showReasons ? 'Hide' : 'Show'} why
          </button>
          {showReasons && (
            <ul className="mt-2 space-y-1 rounded-md bg-slate-50 p-3 text-xs text-slate-600">
              {job.assessment.eligibility_reasons.map((r, i) => (
                <li key={`e-${i}`}>
                  <span className="font-medium">[{r.rule}: {r.result}]</span> {r.detail}
                </li>
              ))}
              {job.assessment.match_reasons.map((r, i) => (
                <li key={`m-${i}`}>
                  <span className="font-medium">
                    [{r.factor}: +{r.contribution}/{r.weight}]
                  </span>{' '}
                  {r.detail}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <a
          href={job.apply_url}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
        >
          View / Apply
        </a>
        {job.state !== 'saved' && (
          <button
            type="button"
            disabled={busy}
            onClick={onSave}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Save
          </button>
        )}
        {job.state === 'saved' && (
          <button
            type="button"
            disabled={busy}
            onClick={onUnsave}
            className="rounded-md border border-slate-300 bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50"
          >
            Saved ✓ (click to unsave)
          </button>
        )}
        {job.state !== 'dismissed' && (
          <button
            type="button"
            disabled={busy}
            onClick={onDismiss}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Dismiss
          </button>
        )}
        {job.state === 'dismissed' && <Badge tone="slate">Dismissed</Badge>}
      </div>
    </li>
  )
}
