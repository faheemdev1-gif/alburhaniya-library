// All requests go through Nginx proxy at /api/
// Nginx forwards them to http://backend:8000/ internally
// This means the browser only ever talks to port 3000 — no cross-port issues
const BASE = '/api'

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, opts)
  if (!res.ok) {
    const err = await res.text()
    throw new Error(err || res.statusText)
  }
  return res.json()
}

export const api = {
  listBooks: () => req('/books/'),

  ingestAll: () => req('/books/ingest-all', { method: 'POST' }),

  uploadBook: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return req('/books/upload', { method: 'POST', body: fd })
  },

  deleteBook: (id) => req(`/books/${id}`, { method: 'DELETE' }),

  search: ({ query, bookIds = [], limit = 2000 }) => {
    const params = new URLSearchParams({ q: query, limit })
    if (bookIds.length) params.set('book_ids', bookIds.join(','))
    return req(`/search/?${params}`)
  },

  getPageText: (bookId, pageNumber) => req(`/books/${bookId}/page/${pageNumber}`),

  fileUrl: (bookId) => `/api/files/${bookId}`,
}
