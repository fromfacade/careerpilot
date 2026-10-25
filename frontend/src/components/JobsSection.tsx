import { useMemo, useState } from 'react'
import { api } from '../api/client'
import type {
  Eligibility,
  EmploymentType,
  JobSort,
  JobState,
  JobView,
  RemoteType,
  RoleCategory,
} from '../api/types'
import { useFetch } from '../hooks/useFetch'
import { JobCard } from './JobCard'
import { ErrorBlock, LoadingBlock } from './StatusViews'

const SORT_OPTIONS: { value: JobSort; label: string }[] = [
  { value: 'score_desc', label: 'Highest match score first' },
  { value: 'score_asc', label: 'Lowest match score first' },
  { value: 'most_eligible_first', label: 'Most eligible first' },
  { value: 'newest_first', label: 'Newest postings first' },
  { value: 'oldest_first', label: 'Oldest postings first' },
  { value: 'company_asc', label: 'Company name A–Z' },
  { value: 'company_desc', label: 'Company name Z–A' },
]

const ROLE_CATEGORY_OPTIONS: { value: RoleCategory; label: string }[] = [
  { value: 'swe_backend', label: 'SWE — Backend' },
  { value: 'swe_frontend', label: 'SWE — Frontend' },
  { value: 'swe_fullstack', label: 'SWE — Full-stack' },
  { value: 'infrastructure', label: 'Infrastructure' },
  { value: 'ai_engineering', label: 'AI Engineering' },
  { value: 'cybersecurity', label: 'Cybersecurity' },
  { value: 'qa', label: 'QA' },
  { value: 'it_support', label: 'IT Support' },
  { value: 'other', label: 'Other' },
]

const EMPLOYMENT_TYPE_OPTIONS: { value: EmploymentType; label: string }[] = [
  { value: 'internship', label: 'Internship' },
  { value: 'new_grad', label: 'New grad' },
  { value: 'full_time', label: 'Full-time' },
  { value: 'contract', label: 'Contract / part-time' },
  { value: 'unknown', label: 'Unknown' },
]

const REMOTE_TYPE_OPTIONS: { value: RemoteType; label: string }[] = [
  { value: 'remote', label: 'Remote' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'onsite', label: 'On-site' },
  { value: 'unknown', label: 'Unknown' },
]

const ELIGIBILITY_OPTIONS: { value: Eligibility; label: string }[] = [
  { value: 'eligible', label: 'Eligible' },
  { value: 'unknown', label: 'Unknown' },
  { value: 'ineligible', label: 'Ineligible' },
]

const STATE_OPTIONS: { value: JobState; label: string }[] = [
  { value: 'new', label: 'Not yet reviewed' },
  { value: 'saved', label: 'Saved' },
  { value: 'dismissed', label: 'Dismissed' },
]

const PAGE_SIZE = 20

interface FilterState {
  minScore: string
  roleCategories: RoleCategory[]
  employmentTypes: EmploymentType[]
  remoteTypes: RemoteType[]
  eligibility: Eligibility[]
  states: JobState[]
  company: string
  location: string
  postedWithinDays: string
}

const EMPTY_FILTERS: FilterState = {
  minScore: '',
  roleCategories: [],
  employmentTypes: [],
  remoteTypes: [],
  eligibility: [],
  states: [],
  company: '',
  location: '',
  postedWithinDays: '',
}

function toggleInList<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value]
}

function isFiltersEmpty(f: FilterState): boolean {
  return (
    f.minScore === '' &&
    f.roleCategories.length === 0 &&
    f.employmentTypes.length === 0 &&
    f.remoteTypes.length === 0 &&
    f.eligibility.length === 0 &&
    f.states.length === 0 &&
    f.company === '' &&
    f.location === '' &&
    f.postedWithinDays === ''
  )
}

function CheckboxGroup<T extends string>({
  legend,
  options,
  selected,
  onToggle,
}: {
  legend: string
  options: { value: T; label: string }[]
  selected: T[]
  onToggle: (value: T) => void
}) {
  return (
    <fieldset>
      <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">{legend}</legend>
      <div className="mt-1.5 flex flex-wrap gap-2">
        {options.map((opt) => (
          <label
            key={opt.value}
            className={`flex cursor-pointer items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium ${
              selected.includes(opt.value)
                ? 'border-blue-600 bg-blue-50 text-blue-700'
                : 'border-slate-300 text-slate-700 hover:bg-slate-50'
            }`}
          >
            <input
              type="checkbox"
              className="sr-only"
              checked={selected.includes(opt.value)}
              onChange={() => onToggle(opt.value)}
            />
            {opt.label}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

export function JobsSection({ refreshSignal }: { refreshSignal: number }) {
  const [view, setView] = useState<JobView>('recommended')
  const [sort, setSort] = useState<JobSort>('score_desc')
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS)
  const [showFilters, setShowFilters] = useState(false)
  const [offset, setOffset] = useState(0)
  const [busyJobId, setBusyJobId] = useState<number | null>(null)

  const params = useMemo(
    () => ({
      view,
      sort,
      limit: PAGE_SIZE,
      offset,
      min_score: filters.minScore === '' ? undefined : Number(filters.minScore),
      role_categories: filters.roleCategories.length ? filters.roleCategories : undefined,
      employment_types: filters.employmentTypes.length ? filters.employmentTypes : undefined,
      remote_types: filters.remoteTypes.length ? filters.remoteTypes : undefined,
      eligibility: filters.eligibility.length ? filters.eligibility : undefined,
      states: filters.states.length ? filters.states : undefined,
      companies: filters.company.trim() ? [filters.company.trim()] : undefined,
      location: filters.location.trim() || undefined,
      posted_within_days: filters.postedWithinDays === '' ? undefined : Number(filters.postedWithinDays),
    }),
    [view, sort, offset, filters],
  )

  const jobs = useFetch(() => api.listJobs(params), [refreshSignal, JSON.stringify(params)])

  function updateFilters(patch: Partial<FilterState>) {
    setOffset(0)
    setFilters((f) => ({ ...f, ...patch }))
  }

  function clearFilters() {
    setOffset(0)
    setFilters(EMPTY_FILTERS)
  }

  function changeView(next: JobView) {
    setOffset(0)
    setView(next)
  }

  function changeSort(next: JobSort) {
    setOffset(0)
    setSort(next)
  }

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

  const total = jobs.status === 'success' ? jobs.data.total : 0
  const pageStart = total === 0 ? 0 : offset + 1
  const pageEnd = jobs.status === 'success' ? Math.min(offset + jobs.data.jobs.length, total) : 0

  return (
    <section aria-labelledby="jobs-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="jobs-heading" className="text-lg font-semibold text-slate-900">
          Jobs
        </h2>

        <div role="group" aria-label="Job view" className="flex gap-1">
          <button
            type="button"
            onClick={() => changeView('recommended')}
            aria-pressed={view === 'recommended'}
            className={`rounded-md px-3 py-1 text-sm font-medium ${
              view === 'recommended' ? 'bg-blue-600 text-white' : 'border border-slate-300 text-slate-700 hover:bg-slate-50'
            }`}
          >
            Recommended
          </button>
          <button
            type="button"
            onClick={() => changeView('all')}
            aria-pressed={view === 'all'}
            className={`rounded-md px-3 py-1 text-sm font-medium ${
              view === 'all' ? 'bg-blue-600 text-white' : 'border border-slate-300 text-slate-700 hover:bg-slate-50'
            }`}
          >
            All Jobs
          </button>
        </div>
      </div>
      {view === 'recommended' && (
        <p className="mt-1 text-xs text-slate-500">
          Shows jobs at/above your minimum match score, excludes roles outside your career scope and dismissed jobs.
          Nothing is deleted — switch to "All Jobs" to see everything ever discovered.
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <label className="text-sm text-slate-600" htmlFor="job-sort">
          Sort by
        </label>
        <select
          id="job-sort"
          value={sort}
          onChange={(e) => changeSort(e.target.value as JobSort)}
          className="rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-700"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        <button
          type="button"
          onClick={() => setShowFilters((v) => !v)}
          aria-expanded={showFilters}
          className="ml-auto rounded-md border border-slate-300 px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          {showFilters ? 'Hide filters' : 'Filters'}
          {!isFiltersEmpty(filters) && (
            <span className="ml-1.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-xs text-white">
              •
            </span>
          )}
        </button>
        <button
          type="button"
          onClick={clearFilters}
          disabled={isFiltersEmpty(filters)}
          className="rounded-md border border-slate-300 px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Clear filters
        </button>
      </div>

      {showFilters && (
        <div className="mt-3 grid gap-4 rounded-md border border-slate-200 bg-slate-50 p-3 sm:grid-cols-2">
          <div>
            <label htmlFor="min-score" className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Minimum match score
            </label>
            <input
              id="min-score"
              type="number"
              min={0}
              max={100}
              placeholder="0"
              value={filters.minScore}
              onChange={(e) => updateFilters({ minScore: e.target.value })}
              className="mt-1.5 w-28 rounded-md border border-slate-300 px-2 py-1 text-sm"
            />
          </div>

          <div>
            <label htmlFor="posted-within" className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Posted within (days)
            </label>
            <input
              id="posted-within"
              type="number"
              min={0}
              placeholder="any time"
              value={filters.postedWithinDays}
              onChange={(e) => updateFilters({ postedWithinDays: e.target.value })}
              className="mt-1.5 w-28 rounded-md border border-slate-300 px-2 py-1 text-sm"
            />
          </div>

          <div>
            <label htmlFor="company-filter" className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Company
            </label>
            <input
              id="company-filter"
              type="text"
              placeholder="e.g. Acme"
              value={filters.company}
              onChange={(e) => updateFilters({ company: e.target.value })}
              className="mt-1.5 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
            />
          </div>

          <div>
            <label htmlFor="location-filter" className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Location
            </label>
            <input
              id="location-filter"
              type="text"
              placeholder="e.g. Seattle, Remote"
              value={filters.location}
              onChange={(e) => updateFilters({ location: e.target.value })}
              className="mt-1.5 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
            />
          </div>

          <div className="sm:col-span-2">
            <CheckboxGroup
              legend="Job category"
              options={ROLE_CATEGORY_OPTIONS}
              selected={filters.roleCategories}
              onToggle={(v) => updateFilters({ roleCategories: toggleInList(filters.roleCategories, v) })}
            />
          </div>

          <CheckboxGroup
            legend="Employment type"
            options={EMPLOYMENT_TYPE_OPTIONS}
            selected={filters.employmentTypes}
            onToggle={(v) => updateFilters({ employmentTypes: toggleInList(filters.employmentTypes, v) })}
          />

          <CheckboxGroup
            legend="Remote / hybrid / on-site"
            options={REMOTE_TYPE_OPTIONS}
            selected={filters.remoteTypes}
            onToggle={(v) => updateFilters({ remoteTypes: toggleInList(filters.remoteTypes, v) })}
          />

          <CheckboxGroup
            legend="Eligibility"
            options={ELIGIBILITY_OPTIONS}
            selected={filters.eligibility}
            onToggle={(v) => updateFilters({ eligibility: toggleInList(filters.eligibility, v) })}
          />

          <CheckboxGroup
            legend="Saved / dismissed status"
            options={STATE_OPTIONS}
            selected={filters.states}
            onToggle={(v) => updateFilters({ states: toggleInList(filters.states, v) })}
          />
        </div>
      )}

      <div className="mt-3">
        {jobs.status === 'loading' && <LoadingBlock label="Loading jobs…" />}
        {jobs.status === 'error' && <ErrorBlock message={jobs.message} onRetry={jobs.reload} />}
        {jobs.status === 'success' && jobs.data.jobs.length === 0 && (
          <p className="text-sm text-slate-500">
            No jobs match these filters yet. Nothing was deleted — try "Clear filters" or switch to "All Jobs".
          </p>
        )}
        {jobs.status === 'success' && jobs.data.jobs.length > 0 && (
          <>
            <ul className="space-y-3">
              {jobs.data.jobs.map((job) => (
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

            <div className="mt-4 flex items-center justify-between text-sm text-slate-600">
              <span>
                Showing {pageStart}–{pageEnd} of {total}
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  className="rounded-md border border-slate-300 px-3 py-1 font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={offset + PAGE_SIZE >= total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                  className="rounded-md border border-slate-300 px-3 py-1 font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </section>
  )
}
