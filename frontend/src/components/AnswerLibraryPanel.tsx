import { useState } from 'react'
import { api } from '../api/client'
import type { AnswerCategory, AnswerStatus, ApplicationAnswer } from '../api/types'
import { isSensitiveCategory, nextStatusAfterApproveClick } from '../knowledge/answerPolicy'
import { useFetch } from '../hooks/useFetch'
import { Badge } from './Badge'
import { EmptyBlock, ErrorBlock, LoadingBlock } from './StatusViews'

const CATEGORY_LABEL: Record<AnswerCategory, string> = {
  interest: 'Interest',
  experience: 'Experience',
  skills: 'Skills',
  logistics: 'Logistics',
  work_authorization: 'Work authorization',
  sponsorship: 'Sponsorship',
  disability: 'Disability',
  veteran: 'Veteran status',
  demographic: 'Demographic',
  criminal_history: 'Criminal history',
  legal_attestation: 'Legal attestation',
  salary: 'Salary',
  other: 'Other',
}

export function AnswerLibraryPanel() {
  const [category, setCategory] = useState<AnswerCategory | ''>('')
  const [status, setStatus] = useState<AnswerStatus | ''>('')
  const [search, setSearch] = useState('')
  const answers = useFetch(
    () => api.listAnswers({ category: category || undefined, status: status || undefined, search: search || undefined }),
    [category, status, search],
  )
  const ai = useFetch(() => api.getAIStatus())
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [question, setQuestion] = useState('')
  const [answerText, setAnswerText] = useState('')
  const [newCategory, setNewCategory] = useState<AnswerCategory>('interest')
  const [preferNot, setPreferNot] = useState(false)

  async function run(action: () => Promise<unknown>, ok?: string) {
    setBusy(true)
    setMessage(null)
    try {
      await action()
      if (ok) setMessage(ok)
      answers.reload()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  const aiAvailable = ai.status === 'success' && ai.data.available

  return (
    <section aria-labelledby="answers-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="answers-heading" className="text-lg font-semibold text-slate-900">
        Answer library
      </h2>
      <p className="mt-1 text-sm text-slate-500">
        Reusable answers for common application questions. AI drafts stay drafts until you approve
        them. Sensitive questions are never inferred and cannot skip review.
      </p>
      {ai.status === 'success' && !ai.data.available && (
        <p className="mt-2 text-xs text-slate-500">
          AI drafts are off ({ai.data.enabled ? 'provider not configured' : 'AI_ENABLED is false'}). Manual answers still work.
        </p>
      )}

      <form
        className="mt-3 space-y-2 rounded-md border border-slate-100 p-2"
        onSubmit={(e) => {
          e.preventDefault()
          run(async () => {
            await api.createAnswer({
              question,
              answer_text: preferNot ? '' : answerText,
              category: newCategory,
              prefer_not_to_answer: preferNot,
            })
            setQuestion('')
            setAnswerText('')
            setPreferNot(false)
          }, 'Saved a draft answer.')
        }}
      >
        <label className="block text-xs">
          <span className="font-medium text-slate-700">Question</span>
          <input value={question} onChange={(e) => setQuestion(e.target.value)} required className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm" />
        </label>
        <label className="block text-xs">
          <span className="font-medium text-slate-700">Answer</span>
          <textarea value={answerText} onChange={(e) => setAnswerText(e.target.value)} rows={3} disabled={preferNot} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm" />
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <select value={newCategory} onChange={(e) => setNewCategory(e.target.value as AnswerCategory)} className="rounded-md border border-slate-300 px-2 py-1 text-sm">
            {(Object.keys(CATEGORY_LABEL) as AnswerCategory[]).map((c) => (
              <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>
            ))}
          </select>
          {isSensitiveCategory(newCategory) && (
            <label className="flex items-center gap-1 text-xs text-slate-700">
              <input type="checkbox" checked={preferNot} onChange={(e) => setPreferNot(e.target.checked)} />
              Prefer not to answer
            </label>
          )}
          <button type="submit" disabled={busy} className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium">
            Save draft
          </button>
          {aiAvailable && (
            <button
              type="button"
              disabled={busy || !question.trim() || isSensitiveCategory(newCategory)}
              onClick={() =>
                run(async () => {
                  const draft = await api.generateAnswer({ question, category: newCategory })
                  setMessage(
                    draft.missing_information.length
                      ? `Draft saved. Missing: ${draft.missing_information.map(String).join(' ')}`
                      : 'AI draft saved. Review it before approving.',
                  )
                })
              }
              className="rounded-md bg-blue-600 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
            >
              Generate AI draft
            </button>
          )}
        </div>
      </form>

      <div className="mt-3 flex flex-wrap gap-2">
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search answers" className="rounded-md border border-slate-300 px-2 py-1 text-sm" />
        <select value={category} onChange={(e) => setCategory(e.target.value as AnswerCategory | '')} className="rounded-md border border-slate-300 px-2 py-1 text-sm">
          <option value="">All categories</option>
          {(Object.keys(CATEGORY_LABEL) as AnswerCategory[]).map((c) => (
            <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>
          ))}
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value as AnswerStatus | '')} className="rounded-md border border-slate-300 px-2 py-1 text-sm">
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="reviewed">Reviewed</option>
          <option value="approved">Approved</option>
        </select>
      </div>

      {message && <p className="mt-2 text-sm text-slate-700" role="status">{message}</p>}
      {answers.status === 'loading' && <LoadingBlock label="Loading answers…" />}
      {answers.status === 'error' && <ErrorBlock message={answers.message} onRetry={answers.reload} />}
      {answers.status === 'success' && answers.data.length === 0 && <EmptyBlock message="No saved answers yet." />}
      {answers.status === 'success' && answers.data.length > 0 && (
        <ul className="mt-3 space-y-2">
          {answers.data.map((answer: ApplicationAnswer) => (
            <li key={answer.id} className="rounded-lg border border-slate-200 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="blue">{CATEGORY_LABEL[answer.category]}</Badge>
                <Badge tone={answer.status === 'approved' ? 'green' : answer.status === 'reviewed' ? 'amber' : 'slate'}>{answer.status}</Badge>
                <Badge tone={answer.origin === 'ai_draft' ? 'amber' : 'slate'}>{answer.origin === 'ai_draft' ? 'AI draft' : 'manual'}</Badge>
                {answer.is_preferred && <Badge tone="blue">Preferred</Badge>}
                {answer.is_sensitive && <Badge tone="amber">Sensitive</Badge>}
              </div>
              <h3 className="mt-1 text-sm font-semibold text-slate-900">{answer.question}</h3>
              <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">
                {answer.prefer_not_to_answer ? 'Prefer not to answer' : answer.answer_text}
              </p>
              {answer.missing_information.length > 0 && (
                <p className="mt-1 text-xs text-amber-800">Missing: {answer.missing_information.map(String).join(' ')}</p>
              )}
              <div className="mt-2 flex flex-wrap gap-2">
                {nextStatusAfterApproveClick(answer.category, answer.status) && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      run(() =>
                        api.updateAnswer(answer.id, {
                          status: nextStatusAfterApproveClick(answer.category, answer.status),
                        }),
                      )
                    }
                    className="rounded-md border border-green-300 px-2 py-1 text-xs text-green-700"
                  >
                    {nextStatusAfterApproveClick(answer.category, answer.status) === 'reviewed' ? 'Mark reviewed' : 'Approve'}
                  </button>
                )}
                <button type="button" disabled={busy} onClick={() => run(() => api.updateAnswer(answer.id, { is_preferred: !answer.is_preferred }))} className="rounded-md border border-slate-300 px-2 py-1 text-xs">
                  {answer.is_preferred ? 'Unmark preferred' : 'Mark preferred'}
                </button>
                <button type="button" disabled={busy} onClick={() => run(() => api.deleteAnswer(answer.id))} className="rounded-md border border-red-300 px-2 py-1 text-xs text-red-700">
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
