import { api } from '../api/client'
import type { AutofillSession } from '../api/types'

const openings = new Map<number, Promise<AutofillSession>>()

export function beginAutofillOpening(
  preparationId: number,
  continueWith: (opened: AutofillSession) => Promise<AutofillSession>,
): Promise<AutofillSession> {
  const existing = openings.get(preparationId)
  if (existing) return existing
  const promise = (async () => {
    const opened = await api.openAutofillSession(preparationId)
    if (opened.state === 'failed' || opened.state === 'cancelled' || opened.state === 'submitted') return opened
    return continueWith(opened)
  })()
  openings.set(preparationId, promise)
  void promise.then(
    (session) => {
      if (session.state === 'failed' || session.state === 'cancelled') openings.delete(preparationId)
    },
    () => openings.delete(preparationId),
  )
  return promise
}

export function releaseAutofillOpening(preparationId: number) {
  openings.delete(preparationId)
}

export function resetAutofillOpenings() {
  openings.clear()
}
