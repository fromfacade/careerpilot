import type { Resume } from '../api/types'

export function deletionRequiresReplacement(resume: Resume, allResumes: Resume[]): boolean {
  return resume.is_primary && allResumes.some((other) => other.id !== resume.id)
}

export function replacementCandidates(resume: Resume, allResumes: Resume[]): Resume[] {
  return allResumes.filter((other) => other.id !== resume.id)
}
