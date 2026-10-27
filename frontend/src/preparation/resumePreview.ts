import { asString, asStringList } from '../resume/factFields'

export type ResumeDetail = Record<string, unknown>

export function resumeHeading(section: string, title: string, detail: ResumeDetail): string {
  if (section === 'work_experience') {
    return [asString(detail.position), asString(detail.employer)].filter(Boolean).join(' — ') || title
  }
  if (section === 'projects') return asString(detail.name) || title
  if (section === 'education') return asString(detail.institution) || title
  return title
}

export function resumeMeta(section: string, detail: ResumeDetail): { label: string; value: string }[] {
  const fields: { key: string; label: string }[] =
    section === 'education'
      ? [
          { key: 'degree', label: 'Degree' },
          { key: 'major', label: 'Major' },
          { key: 'location', label: 'Location' },
          { key: 'dates_text', label: 'Dates' },
          { key: 'gpa', label: 'GPA' },
        ]
      : section === 'work_experience'
        ? [
            { key: 'location', label: 'Location' },
            { key: 'dates_text', label: 'Dates' },
          ]
        : section === 'projects'
          ? [
              { key: 'tagline', label: 'Subtitle' },
              { key: 'technologies', label: 'Technologies' },
              { key: 'dates_text', label: 'Dates' },
            ]
          : section === 'skills'
            ? [{ key: 'items', label: 'Skills' }]
            : [{ key: 'organization', label: 'Organization' }]
  return fields.flatMap((field) => {
    const values = asStringList(detail[field.key])
    const text = values.length ? values.join(', ') : asString(detail[field.key])
    return text ? [{ label: field.label, value: text }] : []
  })
}

export function resumeBullets(detail: ResumeDetail): string[] {
  const bullets = asStringList(detail.bullets)
  if (bullets.length) return bullets
  const text = asString(detail.text)
  return text ? [text] : []
}

export function looksLikeSerializedJson(value: string): boolean {
  return value.includes('{') || value.includes("'name':") || value.includes('"name":')
}