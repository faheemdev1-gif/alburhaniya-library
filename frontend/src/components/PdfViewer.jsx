import { useEffect, useRef, useState, useCallback } from 'react'
import { api } from '../utils/api'

// Load PDF.js from CDN (avoids bundler complexity with worker)
const PDFJS_CDN = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.3.136/pdf.min.mjs'
const WORKER_CDN = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.3.136/pdf.worker.min.mjs'

let pdfjsLib = null
async function getPdfJs() {
  if (pdfjsLib) return pdfjsLib
  const mod = await import(/* @vite-ignore */ PDFJS_CDN)
  mod.GlobalWorkerOptions.workerSrc = WORKER_CDN
  pdfjsLib = mod
  return mod
}

export default function PdfViewer({ bookId, bookTitle, initialPage, onClose }) {
  const canvasRef  = useRef(null)
  const pdfRef     = useRef(null)
  const renderTask = useRef(null)

  const [page, setPage]       = useState(initialPage || 1)
  const [total, setTotal]     = useState(0)
  const [scale, setScale]     = useState(1.4)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  // ── Load PDF ────────────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const lib = await getPdfJs()
        const url = api.fileUrl(bookId)
        const pdf = await lib.getDocument(url).promise
        if (cancelled) return
        pdfRef.current = pdf
        setTotal(pdf.numPages)
        setPage(initialPage || 1)
      } catch (e) {
        if (!cancelled) setError('تعذّر تحميل الملف: ' + e.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [bookId, initialPage])

  // ── Render page ─────────────────────────────────────────────────────────────
  const renderPage = useCallback(async (pageNum) => {
    if (!pdfRef.current || !canvasRef.current) return
    if (renderTask.current) { renderTask.current.cancel(); renderTask.current = null }

    try {
      const pg = await pdfRef.current.getPage(pageNum)
      const viewport = pg.getViewport({ scale })
      const canvas = canvasRef.current
      const ctx = canvas.getContext('2d')
      canvas.width  = viewport.width
      canvas.height = viewport.height

      renderTask.current = pg.render({ canvasContext: ctx, viewport })
      await renderTask.current.promise
    } catch (e) {
      if (e?.name !== 'RenderingCancelledException') console.error(e)
    }
  }, [scale])

  useEffect(() => {
    if (!loading) renderPage(page)
  }, [page, loading, renderPage])

  // ── Keyboard navigation ─────────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowRight' || e.key === 'ArrowUp')   setPage(p => Math.max(1, p - 1))
      if (e.key === 'ArrowLeft'  || e.key === 'ArrowDown')  setPage(p => Math.min(total, p + 1))
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose, total])

  const goTo = (n) => setPage(Math.max(1, Math.min(total, n)))

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-ink/95 backdrop-blur-sm">
      {/* ── Toolbar ── */}
      <div className="flex items-center gap-3 px-5 py-3 bg-ink border-b border-gold/20 flex-shrink-0">
        {/* Close */}
        <button
          onClick={onClose}
          className="text-parch/50 hover:text-parch text-xl leading-none transition-colors"
          title="إغلاق (Esc)"
        >✕</button>

        <div className="flex-1 font-arabic text-parch text-sm truncate">{bookTitle}</div>

        {/* Zoom */}
        <div className="flex items-center gap-1">
          <button onClick={() => setScale(s => Math.max(0.5, s - 0.2))} className="text-parch/60 hover:text-parch px-2 py-1 text-lg">−</button>
          <span className="font-ui text-xs text-parch/50 w-10 text-center">{Math.round(scale * 100)}%</span>
          <button onClick={() => setScale(s => Math.min(3, s + 0.2))} className="text-parch/60 hover:text-parch px-2 py-1 text-lg">+</button>
        </div>

        {/* Page nav */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => goTo(page - 1)}
            disabled={page <= 1}
            className="text-parch/50 hover:text-parch disabled:opacity-20 px-2 transition-colors"
          >→</button>

          <div className="flex items-center gap-1 font-ui text-sm text-parch/70">
            <input
              type="number"
              min={1}
              max={total}
              value={page}
              onChange={e => goTo(parseInt(e.target.value) || 1)}
              className="w-12 bg-white/10 text-parch text-center rounded px-1 py-0.5 focus:outline-none focus:bg-white/20"
            />
            <span className="text-parch/40">/ {total}</span>
          </div>

          <button
            onClick={() => goTo(page + 1)}
            disabled={page >= total}
            className="text-parch/50 hover:text-parch disabled:opacity-20 px-2 transition-colors"
          >←</button>
        </div>
      </div>

      {/* ── Canvas area ── */}
      <div className="flex-1 overflow-auto flex items-start justify-center p-6">
        {error ? (
          <div className="text-rust font-arabic text-center mt-20">
            <p className="text-2xl mb-2">⚠</p>
            <p>{error}</p>
            <p className="font-ui text-xs text-parch/30 mt-2">
              تأكد أن الملف بصيغة PDF لعرضه هنا
            </p>
          </div>
        ) : loading ? (
          <div className="text-parch/40 font-arabic mt-20 text-center">
            <div className="text-3xl mb-3 animate-pulse">📖</div>
            <p>جارٍ تحميل الكتاب…</p>
          </div>
        ) : (
          <div className="pdf-canvas-wrap">
            <canvas ref={canvasRef} />
          </div>
        )}
      </div>

      {/* ── Bottom page strip ── */}
      {!loading && !error && total > 0 && (
        <div className="flex-shrink-0 bg-ink border-t border-gold/10 px-4 py-2 flex items-center justify-center gap-1">
          {/* Thumbnail page buttons — show a window of 9 pages */}
          {Array.from({ length: Math.min(total, 9) }, (_, i) => {
            const offset = Math.max(0, Math.min(total - 9, page - 5))
            const n = offset + i + 1
            return (
              <button
                key={n}
                onClick={() => goTo(n)}
                className={`font-ui text-xs w-7 h-7 rounded transition-colors ${
                  n === page
                    ? 'bg-gold text-ink font-bold'
                    : 'text-parch/40 hover:text-parch hover:bg-white/10'
                }`}
              >{n}</button>
            )
          })}
          {total > 9 && <span className="text-parch/20 font-ui text-xs px-1">…{total}</span>}
        </div>
      )}
    </div>
  )
}
