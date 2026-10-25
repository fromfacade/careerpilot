import { useCallback, useEffect, useState } from 'react'

export type FetchState<T> =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; data: T }

/**
 * Minimal data-fetching hook used everywhere instead of hand-rolled
 * useState/useEffect per component. Deliberately avoids adding a
 * dependency (React Query, SWR, etc.) for Phase 1 — revisit if the number
 * of call sites and caching needs grow.
 */
export function useFetch<T>(fetcher: () => Promise<T>, deps: unknown[] = []): FetchState<T> & { reload: () => void } {
  const [state, setState] = useState<FetchState<T>>({ status: 'loading' })

  const load = useCallback(() => {
    setState({ status: 'loading' })
    fetcher()
      .then((data) => setState({ status: 'success', data }))
      .catch((err: unknown) => setState({ status: 'error', message: err instanceof Error ? err.message : String(err) }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    load()
  }, [load])

  return { ...state, reload: load }
}
