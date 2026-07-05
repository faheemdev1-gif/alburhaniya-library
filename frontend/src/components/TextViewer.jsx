import { useEffect, useState } from 'react'
import { api } from '../utils/api'

export default function TextViewer({ result, onClose }) {
  // currentPage tracks where we are in the book — starts at the matched
  // result's page, then moves with prev/next, independent of the search hit.
  const [currentPage, setCurrentPage] = useState(result.page_number)
  const [pageData, setPageData]   = useState(null)
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState(null)

  // Only show the "matched snippet" highlight box while we're still on the
  // page the search actually matched — once the user flips away it's noise.
  const isMatchedPage = currentPage === result.page_number

  useEffect(() => {
    setCurrentPage(result.page_number)
  }, [result.book_id, result.page_number])

  useEffect(() => {
    let cancelled = false
    async function fetchPage() {
      try {
        setLoading(true)
        setError(null)
        const data = await api.getPageText(result.book_id, currentPage)
        if (!cancelled) setPageData(data)
      } catch (e) {
        if (!cancelled) setError(e.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetchPage()
    return () => { cancelled = true }
  }, [result.book_id, currentPage])

  const goPrev = () => {
    if (pageData?.has_prev ?? currentPage > 1) setCurrentPage((p) => p - 1)
  }
  const goNext = () => {
    if (pageData?.has_next ?? true) setCurrentPage((p) => p + 1)
  }

  // Close on Escape, flip pages with arrow keys (RTL book: ← = next, → = prev)
  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowLeft') goNext()
      else if (e.key === 'ArrowRight') goPrev()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose, pageData, currentPage])

  const pageText = pageData?.text
  const pageLabel = pageData?.page_label || currentPage

  // Highlight the matched query terms in the page text
  function highlightText(text, snippet) {
    if (!snippet || !text) return text
    // Extract plain words from the highlighted snippet
    const plain = snippet.replace(/<[^>]+>/g, '')
    const words = plain.split(/\s+/).filter(w => w.length > 3)
    if (!words.length) return text
    try {
      const pattern = new RegExp(`(${words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'g')
      return text.replace(pattern, '<mark>$1</mark>')
    } catch {
      return text
    }
  }

  const highlighted = isMatchedPage
    ? highlightText(pageText, result.highlight || result.text)
    : pageText

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-ink/90 backdrop-blur-sm">

      {/* ── Toolbar ── */}
      <div className="flex items-center gap-4 px-6 py-3 bg-ink border-b border-gold/20 flex-shrink-0">
        <button
          onClick={onClose}
          className="text-parch/50 hover:text-parch text-xl leading-none transition-colors"
          title="إغلاق (Esc)"
        >✕</button>

        <div className="flex-1 min-w-0">
          <p className="font-arabic text-parch font-semibold truncate">{result.book_title}</p>
          <p className="font-ui text-xs text-parch/40">صفحة {pageLabel}</p>
        </div>

        {/* Prev/Next — RTL book, so "next" (forward through the book) is on the left */}
        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            onClick={goNext}
            disabled={loading || !(pageData?.has_next ?? true)}
            className="px-2 py-1 rounded text-parch/70 hover:text-parch hover:bg-white/10 disabled:opacity-20 disabled:hover:bg-transparent transition-colors"
            title="الصفحة التالية (←)"
          >‹ التالية</button>
          <button
            onClick={goPrev}
            disabled={loading || !(pageData?.has_prev ?? currentPage > 1)}
            className="px-2 py-1 rounded text-parch/70 hover:text-parch hover:bg-white/10 disabled:opacity-20 disabled:hover:bg-transparent transition-colors"
            title="الصفحة السابقة (→)"
          >السابقة ›</button>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {isMatchedPage && !!result.occurrences && (
            <span className="font-ui text-xs bg-gold/20 text-gold px-2 py-1 rounded">
              {result.occurrences} تكرار في الصفحة
            </span>
          )}
          <span className="font-ui text-xs bg-white/10 text-parch/60 px-2 py-1 rounded">
            ص {pageLabel}
            {pageData?.total_pages ? ` / ${pageData.total_pages}` : ''}
          </span>
        </div>
      </div>

      {/* ── Content ── */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-3xl mx-auto px-6 py-10">

          {/* Book + page header */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center gap-2 text-gold/60 text-sm mb-3">
              {'◆ ◇ ◆'.split(' ').map((c, i) => <span key={i}>{c}</span>)}
            </div>
            <h1 className="font-arabic text-2xl font-bold text-parch mb-1">{result.book_title}</h1>
            <p className="font-ui text-sm text-parch/40">الصفحة {pageLabel}</p>
            <div className="inline-flex items-center gap-2 text-gold/60 text-sm mt-3">
              {'◆ ◇ ◆'.split(' ').map((c, i) => <span key={i}>{c}</span>)}
            </div>
          </div>

          {/* Matched snippet highlight box — only while still on the matched page */}
          {isMatchedPage && (
            <div className="bg-gold/10 border border-gold/30 rounded-lg p-4 mb-8">
              <p className="font-ui text-xs text-gold/70 mb-2 text-left">النص المطابق للبحث</p>
              <p
                className="font-arabic text-base leading-loose text-parch/90 text-right"
                dir="rtl"
                dangerouslySetInnerHTML={{ __html: result.highlight || result.text }}
              />
            </div>
          )}

          {/* Full page text */}
          <div className="bg-white/5 rounded-lg p-6">
            <p className="font-ui text-xs text-parch/30 mb-4 text-left">نص الصفحة كاملاً</p>
            {loading ? (
              <div className="space-y-3">
                {Array.from({ length: 8 }).map((_, i) => (
                  <div key={i} className="h-4 rounded shimmer opacity-20" style={{ width: `${70 + Math.random() * 30}%`, marginLeft: 'auto' }} />
                ))}
              </div>
            ) : error ? (
              <p className="font-arabic text-rust text-center py-4">{error}</p>
            ) : (
              <p
                className="font-arabic text-base leading-loose text-parch/80 text-right"
                dir="rtl"
                dangerouslySetInnerHTML={{ __html: highlighted }}
              />
            )}
          </div>

          {/* Bottom page-flip controls */}
          <div className="flex items-center justify-between mt-8">
            <button
              onClick={goNext}
              disabled={loading || !(pageData?.has_next ?? true)}
              className="font-ui text-sm px-4 py-2 rounded bg-white/5 text-parch/70 hover:bg-white/10 hover:text-parch disabled:opacity-20 disabled:hover:bg-white/5 transition-colors"
            >‹ الصفحة التالية</button>
            <span className="font-ui text-xs text-parch/30">
              ص {pageLabel}{pageData?.total_pages ? ` من ${pageData.total_pages}` : ''}
            </span>
            <button
              onClick={goPrev}
              disabled={loading || !(pageData?.has_prev ?? currentPage > 1)}
              className="font-ui text-sm px-4 py-2 rounded bg-white/5 text-parch/70 hover:bg-white/10 hover:text-parch disabled:opacity-20 disabled:hover:bg-white/5 transition-colors"
            >الصفحة السابقة ›</button>
          </div>

          {/* Navigation hint */}
          <div className="text-center mt-4 text-parch/20 text-xs font-ui">
            Press Esc to close · ← / → to flip pages
          </div>
        </div>
      </div>
    </div>
  )
}
