import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../utils/api'

/** The library index, loaded once. */
export function useBooks() {
  const [books, setBooks] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    api
      .listBooks()
      .then((data) => {
        if (!cancelled) setBooks(data)
      })
      .catch((e) => {
        if (!cancelled) setError(e.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return { books, loading, error }
}

/**
 * One search scope. The app runs two of these side by side: one across the
 * whole library, one inside the book currently open.
 */
export function useSearch() {
  const [results, setResults] = useState([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [searched, setSearched] = useState(false)
  const inflight = useRef(null)

  const search = useCallback(async (q, bookIds = []) => {
    const term = (q || '').trim()
    if (!term) return
    inflight.current?.abort()
    const controller = new AbortController()
    inflight.current = controller

    setLoading(true)
    setError(null)
    setQuery(term)
    try {
      const data = await api.search({ query: term, bookIds, signal: controller.signal })
      if (controller.signal.aborted) return
      setResults(data.results)
      setSearched(true)
    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message)
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }, [])

  const clear = useCallback(() => {
    inflight.current?.abort()
    setResults([])
    setQuery('')
    setError(null)
    setSearched(false)
    setLoading(false)
  }, [])

  return { results, query, loading, error, searched, search, clear }
}

/** The page currently on screen in the reader. */
export function usePage(bookId, seq) {
  const [page, setPage] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!bookId || !seq) return
    let cancelled = false
    setLoading(true)
    setError(null)
    api
      .getPage(bookId, seq)
      .then((data) => {
        if (!cancelled) setPage(data)
      })
      .catch((e) => {
        if (!cancelled) setError(e.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [bookId, seq])

  return { page, loading, error }
}
