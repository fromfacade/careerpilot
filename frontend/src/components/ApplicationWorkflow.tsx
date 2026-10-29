import { useRef, useState } from 'react'
import { api } from '../api/client'
import type { ApplicationPreparation, Job } from '../api/types'
import { ApplicationStatusCard } from './ApplicationPreparationPanel'
import { AutofillReview } from './AutofillReview'

export function ApplicationWorkflow({
  job,
  onStarted,
}: {
  job: Job
  onStarted: (preparationId: number) => void
}) {
  const [prep, setPrep] = useState<ApplicationPreparation | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [eligibility, setEligibility] = useState<string | null>(null)
  const [canOpen, setCanOpen] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const starting = useRef(false)

  async function start() {
    if (starting.current) return
    starting.current = true
    setBusy(true)
    setError(null)
    try {
      const result = await api.startApplicationWorkflow(job.id)
      setPrep(result.preparation)
      setMessage(result.message)
      setEligibility(result.eligibility)
      setCanOpen(result.can_open_browser)
      setStatus(result.preparation.application_status ?? null)
      onStarted(result.preparation.id)
    } catch (err) {
      setPrep(null)
      setError(err instanceof Error ? err.message : 'This application could not be started.')
    } finally {
      starting.current = false
      setBusy(false)
    }
  }

  return (
    <>
      <button
        type="button"
        disabled={busy}
        onClick={start}
        className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        Apply with CareerPilot
      </button>
      {error && <p className="mt-2 basis-full text-sm text-red-700">{error.replace(/^API error \d+: /, '')}</p>}
      {prep && (
        <section className="mt-3 basis-full rounded-md border border-slate-200 bg-slate-50 p-3" aria-label="Application workflow">
          <h4 className="text-sm font-semibold text-slate-900">
            {job.title} · {job.employer_name}
          </h4>
          <p className="mt-1 text-sm text-slate-700">Eligibility: {eligibility || job.assessment?.eligibility || 'unknown'}.</p>
          <p className="mt-1 text-sm text-slate-700">Selected resume: {prep.selected_resume_name || 'None'}.</p>
          {prep.resume_selection_reason && <p className="mt-1 text-xs text-slate-600">{prep.resume_selection_reason}</p>}
          {message && <p className="mt-2 text-sm text-slate-700">{message}</p>}
          <ApplicationStatusCard prep={{ ...prep, application_status: status || prep.application_status }} applicationStatus={status || prep.application_status} onResolved={setStatus} />
          {canOpen && <AutofillReview prep={prep} autoStart hideLauncher onApplicationStatus={setStatus} />}
          {!canOpen && <p className="mt-2 text-sm text-amber-800">CareerPilot did not open a browser and did not submit this application.</p>}
        </section>
      )}
    </>
  )
}
