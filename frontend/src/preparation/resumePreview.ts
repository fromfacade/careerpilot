import { asString, asStringList } from '../resume/factFields'

export type ResumeDetail = Record<string, unknown>

const UNICODE_ASCII: Record<string, string> = {
  '\u2022': '-',
  '\u2014': '-',
  '\u2013': '-',
  '\u00b7': '|',
  '\u2018': "'",
  '\u2019': "'",
  '\u201c': '"',
  '\u201d': '"',
}

export function asciiSafe(value: string): string {
  return Object.entries(UNICODE_ASCII).reduce((text, [from, to]) => text.split(from).join(to), value)
}

export function resumeHeading(section: string, title: string, detail: ResumeDetail): string {
  if (section === 'work_experience') {
    return [asString(detail.position), asString(detail.employer)].filter(Boolean).join(' - ') || title
  }
  if (section === 'projects') {
    const name = asString(detail.name) || title
    const tagline = asString(detail.tagline)
    return tagline ? `${name} - ${tagline}` : name
  }
  if (section === 'education') return asString(detail.institution) || asString(detail.school) || title
  if (section === 'skills') return ''
  return title
}

function textValues(value: unknown): string[] {
  const items = asStringList(value)
  if (items.length) return items.map(asciiSafe)
  const single = asciiSafe(asString(value))
  return single ? [single] : []
}

export function resumeSubline(section: string, detail: ResumeDetail): string {
  if (section === 'education') {
    const parts = [
      ...textValues(detail.degree),
      ...textValues(detail.major),
      ...textValues(detail.location),
      ...textValues(detail.dates_text),
    ]
    const gpa = textValues(detail.gpa)
    if (gpa.length) parts.push(`GPA ${gpa[0]}`)
    return parts.join(' | ')
  }
  if (section === 'work_experience') {
    return [...textValues(detail.location), ...textValues(detail.dates_text)].join(' | ')
  }
  if (section === 'projects') {
    const tech = textValues(detail.technologies).join(', ')
    const dates = textValues(detail.dates_text).join(' | ')
    return [tech, dates].filter(Boolean).join(' | ')
  }
  if (section === 'skills') return textValues(detail.items).join(', ')
  return asString(detail.organization)
}

export function resumeBullets(detail: ResumeDetail): string[] {
  const bullets = asStringList(detail.bullets).map(asciiSafe)
  if (bullets.length) return bullets
  const text = asciiSafe(asString(detail.text))
  return text ? [text] : []
}

export function looksLikeSerializedJson(value: string): boolean {
  return value.includes('{') || value.includes("'name':") || value.includes('"name":')
}

export function looksLikeInternalLabel(value: string): boolean {
  return /^(Dates|Subtitle|Skills|Degree|Major|Location|Technologies|School|Employer|Position|Project):/i.test(
    value.trim(),
  )
}
