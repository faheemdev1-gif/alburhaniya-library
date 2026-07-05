import { useState, useEffect, useCallback } from 'react'
import { api } from '../utils/api'

// ── useBooks ──────────────────────────────────────────────────────────────────
export function useBooks() {
  const [books, setBooks]       = useState([])
  const [loading, setLoading]   = useState(true)
  const [ingesting, setIngesting] = useState(false)
  const [error, setError]       = useState(null)

  const refresh = useCallback(async () => {
    try {
      setLoading(true)
      const data = await api.listBooks()
      setBooks(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const ingestAll = useCallback(async () => {
    setIngesting(true)
    try {
      await api.ingestAll()
      // Poll until books appear
      const poll = setInterval(async () => {
        const data = await api.listBooks()
        if (data.length > 0) {
          setBooks(data)
          setIngesting(false)
          clearInterval(poll)
        }
      }, 3000)
    } catch (e) {
      setError(e.message)
      setIngesting(false)
    }
  }, [])

  const uploadBook = useCallback(async (file) => {
    const result = await api.uploadBook(file)
    await refresh()
    return result
  }, [refresh])

  const deleteBook = useCallback(async (id) => {
    await api.deleteBook(id)
    setBooks(prev => prev.filter(b => b.book_id !== id))
  }, [])

  return { books, loading, ingesting, error, refresh, ingestAll, uploadBook, deleteBook }
}

// ── useSearch ─────────────────────────────────────────────────────────────────
export function useSearch() {
  const [results, setResults]   = useState([])
  const [loading, setLoading]   = useState(false)
  const [query, setQuery]       = useState('')
  const [error, setError]       = useState(null)
  const [searched, setSearched] = useState(false)

  const search = useCallback(async (q, bookIds = []) => {
    if (!q.trim()) return
    setLoading(true)
    setError(null)
    setQuery(q)
    try {
      const data = await api.search({ query: q, bookIds })
      setResults(data.results)
      setSearched(true)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  const clear = useCallback(() => {
    setResults([])
    setQuery('')
    setSearched(false)
  }, [])

  return { results, loading, query, error, searched, search, clear }
}
