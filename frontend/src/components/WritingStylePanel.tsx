import { useState } from 'react'
import { api } from '../api/client'
import type {
  WritingComplexity,
  WritingFormality,
  WritingLength,
  WritingSample,
  WritingSampleCategory,
  WritingStyleProfile,
  WritingTechnicalDetail,
  WritingTone,
  WritingVocabulary,
} from '../api/types'
import { useFetch } from '../hooks/useFetch'
import { phrasesToText, textToPhrases } from '../writing/styleForm'
import { Badge } from './Badge'
import { EmptyBlock, ErrorBlock, LoadingBlock } from './StatusViews'

const SAMPLE_LABEL: Record<WritingSampleCategory, string> = {
  technical_experience: 'Technical experience',
  motivation: 'Motivation',
  general: 'General writing',
  other: 'Other',
}

export function WritingStylePanel() {
  const profile = useFetch(() => api.getWritingStyle())
  const samples = useFetch(() => api.listWritingSamples())
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [draft, setDraft] = useState<WritingStyleProfile | null>(null)
  const [avoidDraft, setAvoidDraft] = useState<string | null>(null)
  const form = draft ?? (profile.status === 'success' ? profile.data : null)
  const avoidText = avoidDraft ?? (form ? phrasesToText(form.phrases_to_avoid) : '')
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [category, setCategory] = useState<WritingSampleCategory>('technical_experience')
  const [approveNew, setApproveNew] = useState(true)

  async function run(action: () => Promise<unknown>, ok?: string) {
    setBusy(true)
    setMessage(null)
    try {
      await action()
      if (ok) setMessage(ok)
      setDraft(null)
      setAvoidDraft(null)
      profile.reload()
      samples.reload()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby="writing-style-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="writing-style-heading" className="text-lg font-semibold text-slate-900">
        Writing style
      </h2>
      <p className="mt-1 text-sm text-slate-500">
        Preferences and approved writing samples shape AI drafts. Samples are style references, not
        verified facts, and never submit applications.
      </p>
      {message && (
        <p className="mt-2 text-sm text-slate-700" role="status">
          {message}
        </p>
      )}

      {profile.status === 'loading' && <LoadingBlock label="Loading writing preferences…" />}
      {profile.status === 'error' && <ErrorBlock message={profile.message} onRetry={profile.reload} />}
      {form && (
        <form
          className="mt-3 space-y-2 rounded-md border border-slate-100 p-2"
          onSubmit={(e) => {
            e.preventDefault()
            run(
              () =>
                api.updateWritingStyle({
                  ...form,
                  phrases_to_avoid: textToPhrases(avoidText),
                }),
              'Saved writing preferences.',
            )
          }}
        >
          <h3 className="text-sm font-semibold text-slate-800">Writing preferences</h3>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="block text-xs">
              <span className="font-medium text-slate-700">Tone</span>
              <select
                value={form.tone}
                onChange={(e) => setDraft({ ...form, tone: e.target.value as WritingTone })}
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
              >
                <option value="professional_conversational">Professional but conversational</option>
                <option value="professional">Professional</option>
                <option value="conversational">Conversational</option>
                <option value="formal">Formal</option>
              </select>
            </label>
            <label className="block text-xs">
              <span className="font-medium text-slate-700">Formality</span>
              <select
                value={form.formality}
                onChange={(e) => setDraft({ ...form, formality: e.target.value as WritingFormality })}
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </label>
            <label className="block text-xs">
              <span className="font-medium text-slate-700">Preferred length</span>
              <select
                value={form.preferred_length}
                onChange={(e) => setDraft({ ...form, preferred_length: e.target.value as WritingLength })}
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
              >
                <option value="short">Short</option>
                <option value="short_medium">Short to medium</option>
                <option value="medium">Medium</option>
                <option value="long">Long</option>
              </select>
            </label>
            <label className="block text-xs">
              <span className="font-medium text-slate-700">Sentence complexity</span>
              <select
                value={form.sentence_complexity}
                onChange={(e) => setDraft({ ...form, sentence_complexity: e.target.value as WritingComplexity })}
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
              >
                <option value="simple">Simple</option>
                <option value="moderate">Moderate</option>
                <option value="varied">Varied</option>
              </select>
            </label>
            <label className="block text-xs">
              <span className="font-medium text-slate-700">Technical detail</span>
              <select
                value={form.technical_detail}
                onChange={(e) => setDraft({ ...form, technical_detail: e.target.value as WritingTechnicalDetail })}
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
              >
                <option value="specific">Specific</option>
                <option value="high">High</option>
                <option value="moderate">Moderate</option>
                <option value="low">Low</option>
              </select>
            </label>
            <label className="block text-xs">
              <span className="font-medium text-slate-700">Vocabulary</span>
              <select
                value={form.vocabulary}
                onChange={(e) => setDraft({ ...form, vocabulary: e.target.value as WritingVocabulary })}
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
              >
                <option value="straightforward">Straightforward</option>
                <option value="technical">Technical</option>
                <option value="mixed">Mixed</option>
              </select>
            </label>
          </div>
          <label className="block text-xs">
            <span className="font-medium text-slate-700">Phrases to avoid (one per line)</span>
            <textarea
              value={avoidText}
              onChange={(e) => setAvoidDraft(e.target.value)}
              rows={4}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
          <label className="block text-xs">
            <span className="font-medium text-slate-700">Additional instructions</span>
            <textarea
              value={form.additional_instructions}
              onChange={(e) => setDraft({ ...form, additional_instructions: e.target.value })}
              rows={4}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
          <button type="submit" disabled={busy} className="rounded-md bg-blue-600 px-2 py-1 text-xs font-medium text-white disabled:opacity-50">
            Save preferences
          </button>
        </form>
      )}

      <div className="mt-4">
        <h3 className="text-sm font-semibold text-slate-800">Writing samples</h3>
        <p className="mt-1 text-xs text-slate-500">
          Add your own writing. Approve a sample before CareerPilot uses it as a style reference.
          AI drafts are never stored here unless you adopt them.
        </p>
        <form
          className="mt-2 space-y-2 rounded-md border border-slate-100 p-2"
          onSubmit={(e) => {
            e.preventDefault()
            run(async () => {
              await api.createWritingSample({
                title,
                body,
                category,
                origin: 'user_written',
                is_approved_style_reference: approveNew,
              })
              setTitle('')
              setBody('')
            }, 'Saved writing sample.')
          }}
        >
          <label className="block text-xs">
            <span className="font-medium text-slate-700">Title</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm" />
          </label>
          <label className="block text-xs">
            <span className="font-medium text-slate-700">Sample</span>
            <textarea value={body} onChange={(e) => setBody(e.target.value)} required rows={4} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm" />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <select value={category} onChange={(e) => setCategory(e.target.value as WritingSampleCategory)} className="rounded-md border border-slate-300 px-2 py-1 text-sm">
              {(Object.keys(SAMPLE_LABEL) as WritingSampleCategory[]).map((key) => (
                <option key={key} value={key}>{SAMPLE_LABEL[key]}</option>
              ))}
            </select>
            <label className="flex items-center gap-1 text-xs text-slate-700">
              <input type="checkbox" checked={approveNew} onChange={(e) => setApproveNew(e.target.checked)} />
              Approve as style reference
            </label>
            <button type="submit" disabled={busy} className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium">
              Add sample
            </button>
          </div>
        </form>

        {samples.status === 'loading' && <LoadingBlock label="Loading writing samples…" />}
        {samples.status === 'error' && <ErrorBlock message={samples.message} onRetry={samples.reload} />}
        {samples.status === 'success' && samples.data.length === 0 && <EmptyBlock message="No writing samples yet." />}
        {samples.status === 'success' && samples.data.length > 0 && (
          <ul className="mt-3 space-y-2">
            {samples.data.map((sample: WritingSample) => (
              <li key={sample.id} className="rounded-lg border border-slate-200 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="blue">{SAMPLE_LABEL[sample.category]}</Badge>
                  <Badge tone={sample.origin === 'user_written' ? 'green' : 'amber'}>
                    {sample.origin === 'user_written' ? 'Your writing' : 'Adopted from answer'}
                  </Badge>
                  {sample.is_approved_style_reference && <Badge tone="green">Approved reference</Badge>}
                </div>
                {sample.title && <h4 className="mt-1 text-sm font-semibold text-slate-900">{sample.title}</h4>}
                <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{sample.body}</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      run(() =>
                        api.updateWritingSample(sample.id, {
                          is_approved_style_reference: !sample.is_approved_style_reference,
                        }),
                      )
                    }
                    className="rounded-md border border-slate-300 px-2 py-1 text-xs"
                  >
                    {sample.is_approved_style_reference ? 'Unapprove' : 'Approve for style'}
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => run(() => api.deleteWritingSample(sample.id))}
                    className="rounded-md border border-red-300 px-2 py-1 text-xs text-red-700"
                  >
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
