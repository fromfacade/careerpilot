import { useMemo, useState } from 'react'
import { api } from '../api/client'
import type { CanonicalFact, CanonicalFactStatus, FactType, FactVerificationStatus } from '../api/types'
import { useFetch } from '../hooks/useFetch'
import { FactValueView } from './FactValueView'
import { Badge } from './Badge'
import { EmptyBlock, ErrorBlock, LoadingBlock } from './StatusViews'

const TYPE_LABEL: Record<FactType, string> = {
  education: 'Education',
  skill: 'Skill',
  project: 'Project',
  work_experience: 'Work experience',
  achievement: 'Achievement',
  other: 'Other',
}

function asDisplayFact(fact: CanonicalFact) {
  return {
    id: fact.id,
    candidate_id: fact.candidate_id,
    resume_id: fact.sources[0]?.resume_id ?? null,
    fact_type: fact.fact_type,
    fact_key: fact.fact_key,
    fact_value: fact.fact_value,
    raw_text: null,
    source: 'manual_entry' as const,
    verification_status: fact.verification_status,
    verified_at: fact.verified_at,
    created_at: fact.created_at,
    updated_at: fact.updated_at,
  }
}

export function KnowledgeBasePanel() {
  const [typeFilter, setTypeFilter] = useState<FactType | ''>('')
  const [statusFilter, setStatusFilter] = useState<CanonicalFactStatus | ''>('active')
  const [verifyFilter, setVerifyFilter] = useState<FactVerificationStatus | ''>('')
  const facts = useFetch(
    () =>
      api.listCanonicalFacts({
        fact_type: typeFilter || undefined,
        status: statusFilter || undefined,
        verification_status: verifyFilter || undefined,
      }),
    [typeFilter, statusFilter, verifyFilter],
  )
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [manualKey, setManualKey] = useState('')
  const [manualType, setManualType] = useState<FactType>('other')
  const [manualText, setManualText] = useState('')

  const grouped = useMemo(() => {
    const map = new Map<FactType, CanonicalFact[]>()
    if (facts.status !== 'success') return map
    for (const fact of facts.data) {
      const list = map.get(fact.fact_type) ?? []
      list.push(fact)
      map.set(fact.fact_type, list)
    }
    return map
  }, [facts])

  async function run(action: () => Promise<unknown>, ok?: string) {
    setBusy(true)
    setMessage(null)
    try {
      await action()
      if (ok) setMessage(ok)
      facts.reload()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby="kb-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="kb-heading" className="text-lg font-semibold text-slate-900">
        Candidate knowledge base
      </h2>
      <p className="mt-1 text-sm text-slate-500">
        Authoritative facts used for future applications. They do not belong to a resume. Import
        verified resume records, or add a fact by hand. Conflicts are never applied automatically.
      </p>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            run(async () => {
              const result = await api.importCanonicalFacts()
              setMessage(
                `Imported ${result.created} new, linked ${result.linked} identical, ${result.conflicts} conflict(s), skipped ${result.skipped}.`,
              )
            })
          }
          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Import verified resume facts
        </button>
      </div>

      <form
        className="mt-3 grid gap-2 rounded-md border border-slate-100 p-2 sm:grid-cols-4"
        onSubmit={(e) => {
          e.preventDefault()
          if (!manualKey.trim()) return
          const value = manualType === 'skill' ? { items: manualText.split(',').map((s) => s.trim()).filter(Boolean) } : { text: manualText }
          run(() => api.createCanonicalFact({ fact_type: manualType, fact_key: manualKey.trim(), fact_value: value }), 'Added a manual fact (unverified).')
          setManualKey('')
          setManualText('')
        }}
      >
        <label className="text-xs">
          <span className="font-medium text-slate-700">Type</span>
          <select value={manualType} onChange={(e) => setManualType(e.target.value as FactType)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm">
            {(Object.keys(TYPE_LABEL) as FactType[]).map((t) => (
              <option key={t} value={t}>{TYPE_LABEL[t]}</option>
            ))}
          </select>
        </label>
        <label className="text-xs sm:col-span-1">
          <span className="font-medium text-slate-700">Name</span>
          <input value={manualKey} onChange={(e) => setManualKey(e.target.value)} required className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm" />
        </label>
        <label className="text-xs sm:col-span-2">
          <span className="font-medium text-slate-700">{manualType === 'skill' ? 'Items (comma-separated)' : 'Notes'}</span>
          <input value={manualText} onChange={(e) => setManualText(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm" />
        </label>
        <button type="submit" disabled={busy} className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 sm:col-span-4">
          Add manual fact
        </button>
      </form>

      <div className="mt-3 flex flex-wrap gap-2">
        <label className="text-xs">
          <span className="block font-medium text-slate-700">Type</span>
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as FactType | '')} className="mt-1 rounded-md border border-slate-300 px-2 py-1 text-sm">
            <option value="">All</option>
            {(Object.keys(TYPE_LABEL) as FactType[]).map((t) => (
              <option key={t} value={t}>{TYPE_LABEL[t]}</option>
            ))}
          </select>
        </label>
        <label className="text-xs">
          <span className="block font-medium text-slate-700">Record status</span>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as CanonicalFactStatus | '')} className="mt-1 rounded-md border border-slate-300 px-2 py-1 text-sm">
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="conflict">Conflicts</option>
            <option value="archived">Archived</option>
          </select>
        </label>
        <label className="text-xs">
          <span className="block font-medium text-slate-700">Verification</span>
          <select value={verifyFilter} onChange={(e) => setVerifyFilter(e.target.value as FactVerificationStatus | '')} className="mt-1 rounded-md border border-slate-300 px-2 py-1 text-sm">
            <option value="">All</option>
            <option value="unverified">Unverified</option>
            <option value="verified">Verified</option>
            <option value="edited">Edited</option>
          </select>
        </label>
      </div>

      {message && <p className="mt-2 text-sm text-slate-700" role="status">{message}</p>}
      {facts.status === 'loading' && <LoadingBlock label="Loading knowledge base…" />}
      {facts.status === 'error' && <ErrorBlock message={facts.message} onRetry={facts.reload} />}
      {facts.status === 'success' && facts.data.length === 0 && <EmptyBlock message="No canonical facts match these filters." />}
      {facts.status === 'success' && facts.data.length > 0 && (
        <div className="mt-3 space-y-4">
          {[...grouped.entries()].map(([type, rows]) => (
            <div key={type}>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {TYPE_LABEL[type]} ({rows.length})
              </h3>
              <ul className="mt-2 space-y-2">
                {rows.map((fact) => (
                  <li key={fact.id} className="rounded-lg border border-slate-200 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={fact.status === 'conflict' ? 'amber' : fact.status === 'archived' ? 'slate' : 'blue'}>{fact.status}</Badge>
                      <Badge tone={fact.verification_status === 'verified' ? 'green' : 'slate'}>{fact.verification_status}</Badge>
                      {fact.needs_review && <Badge tone="amber">Needs review</Badge>}
                      <h4 className="text-sm font-semibold text-slate-900">{fact.fact_key}</h4>
                    </div>
                    <FactValueView fact={asDisplayFact(fact)} />
                    {fact.review_reasons.length > 0 && (
                      <ul className="mt-1 list-inside list-disc text-xs text-amber-800">
                        {fact.review_reasons.map((reason, i) => (
                          <li key={i}>{String(reason)}</li>
                        ))}
                      </ul>
                    )}
                    <p className="mt-2 text-xs text-slate-500">
                      Source:{' '}
                      {fact.sources.length === 0
                        ? 'unknown'
                        : fact.sources.map((s) => `${s.origin}${s.resume_id ? ` (resume #${s.resume_id})` : ''}`).join(', ')}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {fact.verification_status !== 'verified' && fact.status === 'active' && (
                        <button type="button" disabled={busy} onClick={() => run(() => api.updateCanonicalFact(fact.id, { verification_status: 'verified' }))} className="rounded-md border border-green-300 px-2 py-1 text-xs text-green-700">
                          Verify
                        </button>
                      )}
                      {fact.status === 'conflict' && (
                        <>
                          <button type="button" disabled={busy} onClick={() => run(() => api.resolveCanonicalConflict(fact.id, 'existing'))} className="rounded-md border border-slate-300 px-2 py-1 text-xs">
                            Keep existing
                          </button>
                          <button type="button" disabled={busy} onClick={() => run(() => api.resolveCanonicalConflict(fact.id, 'incoming'))} className="rounded-md border border-amber-300 px-2 py-1 text-xs text-amber-800">
                            Use this version
                          </button>
                        </>
                      )}
                      {fact.status !== 'archived' && (
                        <button type="button" disabled={busy} onClick={() => run(() => api.archiveCanonicalFact(fact.id))} className="rounded-md border border-slate-300 px-2 py-1 text-xs">
                          Archive
                        </button>
                      )}
                      <button type="button" disabled={busy} onClick={() => run(() => api.deleteCanonicalFact(fact.id), 'Removed from the knowledge base. Extracted resume records were not deleted.')} className="rounded-md border border-red-300 px-2 py-1 text-xs text-red-700">
                        Remove
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
