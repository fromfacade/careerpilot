import type { CandidateFact, FactType } from '../api/types'
import { isFieldAmbiguous } from './reviewPolicy'

export type FieldDef = { key: string; label: string; kind: 'text' | 'list' }

export const EDITABLE_FIELDS: Partial<Record<FactType, FieldDef[]>> = {
  education: [
    { key: 'institution', label: 'School', kind: 'text' },
    { key: 'location', label: 'Location', kind: 'text' },
    { key: 'degree', label: 'Degree', kind: 'text' },
    { key: 'major', label: 'Major', kind: 'text' },
    { key: 'gpa', label: 'GPA', kind: 'text' },
    { key: 'dates_text', label: 'Dates', kind: 'text' },
    { key: 'coursework', label: 'Coursework', kind: 'text' },
    { key: 'bullets', label: 'Bullets (one per line)', kind: 'list' },
  ],
  work_experience: [
    { key: 'employer', label: 'Employer', kind: 'text' },
    { key: 'position', label: 'Position', kind: 'text' },
    { key: 'location', label: 'Location', kind: 'text' },
    { key: 'dates_text', label: 'Dates', kind: 'text' },
    { key: 'bullets', label: 'Accomplishments (one per line)', kind: 'list' },
  ],
  project: [
    { key: 'name', label: 'Project name', kind: 'text' },
    { key: 'tagline', label: 'Subtitle', kind: 'text' },
    { key: 'technologies', label: 'Technologies (comma-separated)', kind: 'list' },
    { key: 'dates_text', label: 'Dates', kind: 'text' },
    { key: 'bullets', label: 'Description (one per line)', kind: 'list' },
  ],
  skill: [{ key: 'items', label: 'Skills (comma-separated)', kind: 'list' }],
  achievement: [{ key: 'text', label: 'Achievement', kind: 'text' }],
  other: [{ key: 'text', label: 'Text', kind: 'text' }],
}

export function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

export function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

const COMMA_LIST_KEYS = new Set(['technologies', 'items'])

export function isCommaList(field: FieldDef): boolean {
  return field.kind === 'list' && COMMA_LIST_KEYS.has(field.key)
}

export function fieldValue(fact: CandidateFact, field: FieldDef): string {
  const raw = fact.fact_value[field.key]
  if (field.kind === 'list') {
    const items = asStringList(raw)
    return isCommaList(field) ? items.join(', ') : items.join('\n')
  }
  return asString(raw)
}

export function applyFieldValue(current: Record<string, unknown>, field: FieldDef, text: string): Record<string, unknown> {
  if (field.kind === 'list') {
    const splitter = isCommaList(field) ? ',' : '\n'
    return {
      ...current,
      [field.key]: text
        .split(splitter)
        .map((item) => item.trim())
        .filter(Boolean),
    }
  }
  const trimmed = text.trim()
  return { ...current, [field.key]: trimmed === '' ? null : trimmed }
}

export type SummaryRow = { key: string; label: string; value: string; ambiguous: boolean }

const ROW_DEFS: Partial<Record<FactType, { key: string; label: string }[]>> = {
  education: [
    { key: 'institution', label: 'School' },
    { key: 'location', label: 'Location' },
    { key: 'degree', label: 'Degree' },
    { key: 'major', label: 'Major' },
    { key: 'gpa', label: 'GPA' },
    { key: 'dates_text', label: 'Dates' },
    { key: 'coursework', label: 'Coursework' },
  ],
  work_experience: [
    { key: 'employer', label: 'Employer' },
    { key: 'position', label: 'Position' },
    { key: 'location', label: 'Location' },
    { key: 'dates_text', label: 'Dates' },
  ],
  project: [
    { key: 'name', label: 'Project' },
    { key: 'tagline', label: 'Subtitle' },
    { key: 'dates_text', label: 'Dates' },
  ],
  achievement: [{ key: 'organization', label: 'Organization' }],
}

/**
 * The labelled single-value rows for a record. A field the parser could not
 * determine is shown as "Not determined" when it was flagged ambiguous, so a
 * blank never silently looks like a confident empty value. Unflagged empty
 * optional fields are omitted. Nothing is ever invented.
 */
export function summaryRows(fact: CandidateFact): SummaryRow[] {
  const rows: SummaryRow[] = []
  for (const def of ROW_DEFS[fact.fact_type] ?? []) {
    const value = asString(fact.fact_value[def.key])
    const ambiguous = isFieldAmbiguous(fact, def.key)
    if (value) rows.push({ ...def, value, ambiguous })
    else if (ambiguous) rows.push({ ...def, value: 'Not determined', ambiguous })
  }
  return rows
}
