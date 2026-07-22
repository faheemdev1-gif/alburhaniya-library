import { useCallback, useEffect, useState } from 'react'
import Header from './components/Header'
import LibraryView from './components/LibraryView'
import SearchResults from './components/SearchResults'
import ReaderView from './components/ReaderView'
import { useBooks, useSearch } from './hooks/useLibrary'

const SIZES = ['1.05rem', '1.18rem', '1.3rem', '1.45rem', '1.6rem', '1.8rem']
const DEFAULT_SIZE = 2

function readStored(key, fallback) {
  try {
    const v = window.localStorage.getItem(key)
    return v === null ? fallback : JSON.parse(v)
  } catch {
    return fallback
  }
}

function store(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* private mode — reading preferences just won't persist */
  }
}

export default function App() {
  const { books, loading: booksLoading, error: booksError } = useBooks()

  // Two scopes, side by side: the whole library, and the book that is open.
  const libSearch = useSearch()
  const bookSearch = useSearch()

  const [reading, setReading] = useState(null) // { book, seq }
  const [draft, setDraft] = useState('')

  const [theme, setTheme] = useState(() => readStored('bl.theme', 'day'))
  const [sizeStep, setSizeStep] = useState(() => readStored('bl.size', DEFAULT_SIZE))

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    store('bl.theme', theme)
  }, [theme])

  useEffect(() => {
    document.documentElement.style.setProperty('--reading-size', SIZES[sizeStep])
    store('bl.size', sizeStep)
  }, [sizeStep])

  const openBook = useCallback(
    (book, seq = 1, carryQuery = null) => {
      setReading({ book, seq })
      if (carryQuery) {
        setDraft(carryQuery)
        bookSearch.search(carryQuery, [book.book_id])
      } else {
        setDraft('')
        bookSearch.clear()
      }
    },
    [bookSearch]
  )

  const openResult = useCallback(
    (result) => {
      const book =
        books.find((b) => b.book_id === result.book_id) || {
          book_id: result.book_id,
          title: result.book_title,
          page_count: 0,
        }
      openBook(book, result.seq, libSearch.query)
    },
    [books, libSearch.query, openBook]
  )

  const backToLibrary = useCallback(() => {
    setReading(null)
    setDraft(libSearch.query)
    bookSearch.clear()
  }, [bookSearch, libSearch.query])

  // Same query, widened from this book to the whole library.
  const widenScope = useCallback(() => {
    const term = (draft || bookSearch.query).trim()
    setReading(null)
    bookSearch.clear()
    if (term) libSearch.search(term)
  }, [draft, bookSearch, libSearch])

  const searchProps = reading
    ? {
        scopeLabel: 'هذا الكتاب',
        placeholder: `ابحث في «${reading.book.title}»…`,
        loading: bookSearch.loading,
        value: bookSearch.query,
        onChange: setDraft,
        onSubmit: (q) => bookSearch.search(q, [reading.book.book_id]),
        onClear: bookSearch.clear,
        onEscapeScope: (draft || bookSearch.query).trim() ? widenScope : null,
        escapeLabel: `ابحث عن «${(draft || bookSearch.query).trim()}» في كل الكتب ←`,
      }
    : {
        scopeLabel: 'كل الكتب',
        placeholder: books.length ? `ابحث في ${books.length} كتاباً…` : 'ابحث في المكتبة…',
        loading: libSearch.loading,
        value: libSearch.query,
        onChange: setDraft,
        onSubmit: (q) => libSearch.search(q),
        onClear: libSearch.clear,
        autoFocus: true,
      }

  return (
    <div className="min-h-screen flex flex-col">
      <Header
        book={reading?.book}
        onBack={backToLibrary}
        search={searchProps}
        theme={theme}
        onToggleTheme={() => setTheme((t) => (t === 'night' ? 'day' : 'night'))}
        onZoom={(d) => setSizeStep((s) => Math.min(SIZES.length - 1, Math.max(0, s + d)))}
        canZoomIn={sizeStep < SIZES.length - 1}
        canZoomOut={sizeStep > 0}
      />

      <main className="flex-1 w-full max-w-6xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
        {reading ? (
          <ReaderView
            book={reading.book}
            seq={reading.seq}
            onSeq={(seq) => setReading((r) => ({ ...r, seq }))}
            search={bookSearch}
            onCloseSearch={bookSearch.clear}
          />
        ) : libSearch.searched || libSearch.loading ? (
          <SearchResults
            results={libSearch.results}
            query={libSearch.query}
            loading={libSearch.loading}
            error={libSearch.error}
            onOpen={openResult}
            onClearSearch={libSearch.clear}
          />
        ) : (
          <LibraryView
            books={books}
            loading={booksLoading}
            error={booksError}
            onOpen={(book) => openBook(book)}
          />
        )}
      </main>

      <footer
        className="border-t py-5 text-center font-ui text-[0.65rem]"
        style={{ borderColor: 'var(--paper-edge)', color: 'var(--ink-faint)' }}
      >
        المكتبة البرهانية · بحث بالكلمة المجرّدة من التشكيل
      </footer>
    </div>
  )
}
