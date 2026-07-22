// In development Vite proxies /api to the backend; in production the host
// rewrites /api/* onto the deployed backend, so the browser stays on one
// origin and never needs CORS.
//
// Set VITE_API_BASE at build time to call the backend directly instead —
// useful on a host without rewrite rules. The backend sends
// Access-Control-Allow-Origin: *, so cross-origin calls work too.
const BASE = import.meta.env.VITE_API_BASE || '/api'

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, opts)
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(body || res.statusText || 'تعذّر الاتصال بالخادم')
  }
  return res.json()
}

export const api = {
  /** [{ book_id, title, page_count, source_grade, source_code }] */
  listBooks: () => req('/books/'),

  /** One page: { text, printed_page, book_title, total_pages, has_prev, has_next } */
  getPage: (bookId, seq) => req(`/books/${bookId}/page/${seq}`),

  /**
   * Exact-word search, one result per matching page.
   * Pass bookIds to scope it to a single book (or a few).
   */
  search: ({ query, bookIds = [], limit = 2000, signal }) => {
    const params = new URLSearchParams({ q: query, limit: String(limit) })
    if (bookIds.length) params.set('book_ids', bookIds.join(','))
    return req(`/search/?${params}`, { signal })
  },
}
