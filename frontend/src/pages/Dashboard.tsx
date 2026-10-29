import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { DiscoveryPanel } from '../components/DiscoveryPanel'
import { JobSourcesPanel } from '../components/JobSourcesPanel'
import { ApplicationPreparationPanel } from '../components/ApplicationPreparationPanel'
import { JobsSection } from '../components/JobsSection'
import { PreferencesPanel } from '../components/PreferencesPanel'
import { ProfilePanel } from '../components/ProfilePanel'
import { AnswerLibraryPanel } from '../components/AnswerLibraryPanel'
import { KnowledgeBasePanel } from '../components/KnowledgeBasePanel'
import { WritingStylePanel } from '../components/WritingStylePanel'
import { ResumePanel } from '../components/ResumePanel'
import { ErrorBlock } from '../components/StatusViews'

export function Dashboard() {
  // The job card starts an application. This page only remembers which one.
  const [refreshSignal, setRefreshSignal] = useState(0)
  const [backendDown, setBackendDown] = useState<string | null>(null)
  const [preparationId, setPreparationId] = useState<number | null>(null)

  const bump = useCallback(() => setRefreshSignal((n) => n + 1), [])

  useEffect(() => {
    api
      .health()
      .then((h) => setBackendDown(h.database !== 'ok' ? `Database connectivity issue: ${h.database}` : null))
      .catch((err) => setBackendDown(err instanceof Error ? err.message : 'Backend unreachable'))
  }, [])

  return (
    <main className="mx-auto max-w-5xl space-y-6 p-4 sm:p-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">CareerPilot</h1>
        <p className="text-sm text-slate-500">
          Local-first job search, verified facts, and a reusable answer library. A Greenhouse application is sent only after you confirm that specific job.
        </p>
      </header>

      {backendDown && (
        <ErrorBlock message={`Cannot reach the backend API: ${backendDown}. Is uvicorn running on port 8000?`} />
      )}

      <ProfilePanel onChanged={bump} />
      <PreferencesPanel onChanged={bump} />
      <ResumePanel />
      <KnowledgeBasePanel />
      <WritingStylePanel />
      <AnswerLibraryPanel />
      <JobSourcesPanel />
      <DiscoveryPanel onRunCompleted={bump} />
      <JobsSection
        refreshSignal={refreshSignal}
        onStarted={setPreparationId}
      />
      <ApplicationPreparationPanel selectedId={preparationId} onSelected={setPreparationId} />
    </main>
  )
}
