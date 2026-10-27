import { useState } from 'react'
import type { Job, MatchReason } from '../api/types'
import { Badge } from './Badge'

const ELIGIBILITY_TONE: Record<string, 'green' | 'red' | 'amber'> = {
  eligible: 'green',
  ineligible: 'red',
  unknown: 'amber',
}

// Deliberately a distinct mapping from eligibility's, and always rendered
// with its own "Relevance:" label -- a job can be `eligible` (no hard
// requirement blocks it) and still `not_relevant` (outside career scope),
// and the two must never be visually conflated into one verdict.
const RELEVANCE_TONE: Record<string, 'green' | 'red' | 'amber'> = {
  relevant: 'green',
  not_relevant: 'red',
  unknown: 'amber',
}

const RELEVANCE_LABEL: Record<string, string> = {
  relevant: 'relevant',
  not_relevant: 'not relevant to your search',
  unknown: 'relevance unknown',
}

function formatDate(value: string | null): string | null {
  if (!value) return null
  try {
    return new Date(value).toLocaleDateString()
  } catch {
    return value
  }
}

/** A single always-visible line explaining *why* this job landed where it
 * did in the ranking -- Priority 4 requires every card show a reason, not
 * just a score. Falls back explicitly to "not yet scored" rather than
 * silently showing nothing when there's no assessment at all. */
function rankingReason(job: Job): string {
  const a = job.assessment
  if (!a) return 'Not yet scored for your profile.'

  if (a.relevance === 'not_relevant') {
    const detail = a.relevance_reasons[0]?.detail
    return detail ? `Outside your career scope: ${detail}` : 'Classified as outside your career scope.'
  }

  const topMatch = [...a.match_reasons]
    .filter((r): r is MatchReason & { contribution: number } => typeof r.contribution === 'number')
    .sort((x, y) => (y.contribution ?? 0) - (x.contribution ?? 0))[0]
  if (topMatch) {
    return `Match score driven mainly by: ${topMatch.detail}`
  }
  return 'Score computed from your preferences (see details below).'
}

export function JobCard({
  job,
  onSave,
  onDismiss,
  onUnsave,
  onPrepare,
  busy,
}: {
  job: Job
  onSave: () => void
  onDismiss: () => void
  onUnsave: () => void
  onPrepare: () => void
  busy: boolean
}) {
  const [showReasons, setShowReasons] = useState(false)
  const postedLabel = formatDate(job.posted_at)

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
            <span className="text-sm font-semibold text-slate-700">Match: {job.assessment.match_score}/100</span>
            <Badge tone={ELIGIBILITY_TONE[job.assessment.eligibility]}>Eligibility: {job.assessment.eligibility}</Badge>
            <Badge tone={RELEVANCE_TONE[job.assessment.relevance]}>Relevance: {RELEVANCE_LABEL[job.assessment.relevance]}</Badge>
          </div>
        )}
        {!job.assessment && <Badge tone="slate">Not yet scored</Badge>}
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        <Badge>{job.employment_type.replace('_', ' ')}</Badge>
        <Badge>{job.role_category.replace('_', ' ')}</Badge>
        <Badge>{job.remote_type}</Badge>
        {!job.is_active && <Badge tone="amber">no longer listed</Badge>}
      </div>

      <p className="mt-2 text-sm text-slate-600">
        {job.locations.map((l) => l.raw_text).join(', ') || 'Location unspecified'}
        {' · '}
        {postedLabel ? `posted ${postedLabel}` : 'posting date unverified'}
      </p>

      <p className="mt-2 text-sm text-slate-700">
        <span className="font-medium">Why this ranking: </span>
        {rankingReason(job)}
      </p>

      {job.assessment &&
        (job.assessment.eligibility_reasons.length > 0 ||
          job.assessment.relevance_reasons.length > 0 ||
          job.assessment.match_reasons.length > 0) && (
          <div className="mt-2">
            <button
              type="button"
              className="text-xs font-medium text-blue-700 underline-offset-2 hover:underline"
              onClick={() => setShowReasons((v) => !v)}
              aria-expanded={showReasons}
            >
              {showReasons ? 'Hide' : 'Show'} full explanation
            </button>
            {showReasons && (
              <ul className="mt-2 space-y-1 rounded-md bg-slate-50 p-3 text-xs text-slate-600">
                {job.assessment.eligibility_reasons.map((r, i) => (
                  <li key={`e-${i}`}>
                    <span className="font-medium">
                      [eligibility / {r.rule}: {r.result}]
                    </span>{' '}
                    {r.detail}
                  </li>
                ))}
                {job.assessment.relevance_reasons.map((r, i) => (
                  <li key={`r-${i}`}>
                    <span className="font-medium">
                      [relevance / {r.rule}: {r.result}]
                    </span>{' '}
                    {r.detail}
                  </li>
                ))}
                {job.assessment.match_reasons.map((r, i) => (
                  <li key={`m-${i}`}>
                    <span className="font-medium">
                      [score / {r.factor}: {r.contribution != null && r.contribution >= 0 ? '+' : ''}
                      {r.contribution}
                      {r.weight != null ? `/${r.weight}` : ''}]
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
          href={job.canonical_url}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          View original posting
        </a>
        <button
          type="button"
          disabled={busy}
          onClick={onPrepare}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Prepare application
        </button>
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
