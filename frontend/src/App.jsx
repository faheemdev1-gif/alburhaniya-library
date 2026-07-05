import { useState } from 'react'
import Header from './components/Header'
import BookSelector from './components/BookSelector'
import SearchBar from './components/SearchBar'
import ResultsPanel from './components/ResultsPanel'
import TextViewer from './components/TextViewer'
import { ToastContainer, useToast } from './components/Toast'
import { useBooks, useSearch } from './hooks/useLibrary'

export default function App() {
  const { books, loading: booksLoading, ingesting, ingestAll, uploadBook, deleteBook } = useBooks()
  const { results, loading: searchLoading, query, error, searched, search, clear } = useSearch()
  const { toasts, toast } = useToast()

  const [selectedIds, setSelectedIds] = useState([])
  const [viewer, setViewer] = useState(null) // full result object

  const toggleBook = (id) => {
    setSelectedIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }
  const selectAll = () => setSelectedIds(books.map(b => b.book_id))
  const clearAll  = () => setSelectedIds([])

  const handleSearch = (q) => {
    if (books.length === 0) { toast('لا توجد كتب مفهرسة بعد', 'error'); return }
    search(q, selectedIds)
  }

  const handleUpload = async (file) => {
    try {
      toast('جارٍ رفع الكتاب وفهرسته…')
      const result = await uploadBook(file)
      toast(`تمت الفهرسة: ${result.title}`)
    } catch (e) {
      toast('فشل الرفع: ' + e.message, 'error')
    }
  }

  const handleIngestAll = async () => {
    toast('بدأت الفهرسة في الخلفية، قد تستغرق بضع دقائق…')
    await ingestAll()
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header />

      <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-8 flex gap-8">
        <BookSelector
          books={books}
          loading={booksLoading}
          ingesting={ingesting}
          selectedIds={selectedIds}
          onToggle={toggleBook}
          onSelectAll={selectAll}
          onClearAll={clearAll}
          onIngestAll={handleIngestAll}
          onUpload={handleUpload}
          onDelete={async (id) => { await deleteBook(id); toast('تم حذف الكتاب') }}
        />

        <div className="flex-1 flex flex-col gap-6 min-w-0">
          <div className="ornament">
            <span className="font-arabic text-sm text-ink/40 px-3">البحث الذكي</span>
          </div>

          <SearchBar
            onSearch={handleSearch}
            loading={searchLoading}
            selectedCount={selectedIds.length || books.length}
            totalBooks={books.length}
          />

          {error && (
            <div className="bg-rust/10 border border-rust/30 rounded p-3 font-arabic text-sm text-rust">
              {error}
            </div>
          )}

          <ResultsPanel
            results={results}
            loading={searchLoading}
            searched={searched}
            query={query}
            onOpen={setViewer}
          />
        </div>
      </main>

      {/* ── Text Viewer modal ── */}
      {viewer && (
        <TextViewer
          result={viewer}
          onClose={() => setViewer(null)}
        />
      )}

      <ToastContainer toasts={toasts} />
    </div>
  )
}
