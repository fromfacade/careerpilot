import type { CandidateFact } from '../api/types'
import { asString, asStringList, summaryRows } from '../resume/factFields'
import { awaitsReview, reviewReasons } from '../resume/reviewPolicy'
import { Badge } from './Badge'

/** Explains why the parser is unsure. Shown only while the record is unreviewed. */
export function ReviewNotice({ fact }: { fact: CandidateFact }) {
  if (!awaitsReview(fact)) return null
  const reasons = reviewReasons(fact)
  return (
    <div role="note" className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
      <p className="font-semibold">Check this record before verifying</p>
      {reasons.length > 0 ? (
        <ul className="mt-1 list-inside list-disc space-y-0.5">
          {reasons.map((reason, i) => (
            <li key={i}>{reason}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-1">The parser was not confident about some fields.</p>
      )}
      <p className="mt-1 text-amber-800">
        Flagged records are skipped by &ldquo;Verify selected&rdquo;; verify or edit them individually.
      </p>
    </div>
  )
}

export function FactValueView({ fact }: { fact: CandidateFact }) {
  const v = fact.fact_value
  const rows = summaryRows(fact)
  const bullets = asStringList(v.bullets)
  const items = asStringList(v.items)
  const technologies = asStringList(v.technologies)
  const unclassified = asStringList(v.unclassified_text)
  const text = fact.fact_type === 'achievement' && bullets.length > 0 ? '' : asString(v.text)

  return (
    <div className="mt-2 space-y-1 text-sm text-slate-700">
      {rows.map((row) => (
        <p key={row.key} className={row.ambiguous ? 'rounded bg-amber-50 px-1 text-amber-900' : undefined}>
          <span className="font-medium text-slate-500">{row.label}: </span>
          {row.value}
          {row.ambiguous && <span className="ml-1 text-xs font-semibold">(check)</span>}
        </p>
      ))}
      {unclassified.length > 0 && (
        <p className="rounded bg-amber-50 px-1 text-amber-900">
          <span className="font-medium">Unclassified header text: </span>
          {unclassified.join(' / ')}
        </p>
      )}
      {items.length > 0 && (
        <div className="flex flex-wrap gap-1" aria-label="Skills">
          {items.map((item, i) => (
            <Badge key={i} tone="slate">
              {item}
            </Badge>
          ))}
        </div>
      )}
      {technologies.length > 0 && (
        <div className="flex flex-wrap items-center gap-1" aria-label="Technologies">
          <span className="text-xs font-medium text-slate-500">Technologies:</span>
          {technologies.map((item, i) => (
            <Badge key={i} tone="slate">
              {item}
            </Badge>
          ))}
        </div>
      )}
      {bullets.length > 0 && (
        <ul className="list-inside list-disc space-y-0.5">
          {bullets.map((bullet, i) => (
            <li key={i}>{bullet}</li>
          ))}
        </ul>
      )}
      {text && <p>{text}</p>}
      {rows.length === 0 && items.length === 0 && technologies.length === 0 && bullets.length === 0 && !text && (
        <pre className="whitespace-pre-wrap text-xs text-slate-500">{JSON.stringify(fact.fact_value)}</pre>
      )}
    </div>
  )
}
