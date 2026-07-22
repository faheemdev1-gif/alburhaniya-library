import { useEffect, useMemo, useState } from 'react'
import PageText from './PageText'
import { usePage } from '../hooks/useLibrary'
import { buildMatchRegex } from '../utils/arabic'

function NavButton({ onClick, disabled, children, title }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="px-3 py-2 rounded font-arabic text-sm transition-colors disabled:opacity-25 disabled:cursor-not-allowed"
      style={{ color: 'var(--ink-muted)', background: 'var(--paper-raised)', border: '1px solid var(--paper-edge)' }}
    >
      {children}
    </button>
  )
}

/** Jump straight to a page by its sequence number. */
function PageJump({ seq, total, onGo }) {
  const [draft, setDraft] = useState(String(seq))
  useEffect(() => setDraft(String(seq)), [seq])

  const commit = () => {
    const n = parseInt(draft, 10)
    if (Number.isFinite(n) && n >= 1 && n <= total) onGo(n)
    else setDraft(String(seq))
  }

  return (
    <span className="font-ui text-xs flex items-center gap-1.5" style={{ color: 'var(--ink-faint)' }}>
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value.replace(/\D/g, ''))}
        onBlur={commit}
        onKeyDown={(e) => e.key === 'Enter' && commit()}
        aria-label="الانتقال إلى صفحة"
        className="w-14 text-center py-1 rounded bg-transparent border focus:outline-none"
        style={{ borderColor: 'var(--paper-edge)', color: 'var(--ink)' }}
      />
      <span>/ {total}</span>
    </span>
  )
}

/** The in-book hit list — every page of this book the word appears on. */
function HitList({ search, currentSeq, onGo, onClose }) {
  if (search.loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-14 rounded shimmer" />
        ))}
      </div>
    )
  }

  if (!search.searched) return null

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 mb-3">
        <p className="font-arabic text-sm" style={{ color: 'var(--ink-muted)' }}>
          {search.results.length
            ? `${search.results.length} صفحة في هذا الكتاب`
            : 'لا نتائج في هذا الكتاب'}
        </p>
        <button
          onClick={onClose}
          className="font-ui text-xs underline underline-offset-2"
          style={{ color: 'var(--ink-faint)' }}
        >
          إغلاق
        </button>
      </div>

      {!search.results.length && (
        <p className="font-arabic text-xs leading-relaxed" style={{ color: 'var(--ink-faint)' }}>
          الكلمة «{search.query}» غير موجودة هنا. جرّب البحث في المكتبة كلها من الرابط أسفل الحقل.
        </p>
      )}

      <ul className="space-y-1.5 max-h-[60vh] overflow-y-auto pl-1">
        {search.results.map((r) => {
          const active = r.seq === currentSeq
          return (
            <li key={r.seq}>
              <button
                onClick={() => onGo(r.seq)}
                className="w-full text-right p-2.5 rounded transition-colors"
                style={{
                  background: active ? 'color-mix(in srgb, var(--gold) 14%, transparent)' : 'transparent',
                  border: `1px solid ${active ? 'var(--gold-soft)' : 'transparent'}`,
                }}
              >
                <span className="flex items-center justify-between gap-2 mb-1">
                  <span className="font-arabic text-xs" style={{ color: 'var(--ink)' }}>
                    {r.page_label}
                  </span>
                  <span className="font-ui text-[0.65rem]" style={{ color: 'var(--ink-faint)' }}>
                    {r.occurrences}×
                  </span>
                </span>
                <span
                  className="font-arabic text-xs leading-relaxed line-clamp-3 block"
                  style={{ color: 'var(--ink-muted)' }}
                  dir="rtl"
                  dangerouslySetInnerHTML={{ __html: r.snippet }}
                />
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export default function ReaderView({ book, seq, onSeq, search, onCloseSearch }) {
  const { page, loading, error } = usePage(book.book_id, seq)
  // Until the page arrives we do not know the length of the book; fall back
  // to where we are so navigation never disables itself wrongly.
  const total = page?.total_pages || book.page_count || seq

  const match = useMemo(() => buildMatchRegex(search.query), [search.query])
  const showHits = search.searched

  const go = (n) => {
    if (n >= 1 && n <= total) onSeq(n)
  }

  // Every page starts at the top, the way turning a leaf does.
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'auto' })
  }, [seq])

  // RTL book: ← moves forward, → moves back.
  useEffect(() => {
    const onKey = (e) => {
      const typing = /^(INPUT|TEXTAREA)$/.test(document.activeElement?.tagName || '')
      if (typing) return
      if (e.key === 'ArrowLeft') go(seq + 1)
      if (e.key === 'ArrowRight') go(seq - 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [seq, total])

  return (
    <div className={`flex gap-8 ${showHits ? 'lg:flex-row' : ''} flex-col lg:flex-row`}>
      {showHits && (
        <aside
          className="lg:w-72 lg:shrink-0 lg:order-2 card p-3.5 lg:sticky lg:top-24 lg:self-start"
          aria-label="نتائج البحث في هذا الكتاب"
        >
          <HitList search={search} currentSeq={seq} onGo={go} onClose={onCloseSearch} />
        </aside>
      )}

      <article className="flex-1 min-w-0 lg:order-1">
        <div className="text-center mb-8">
          <h1 className="font-arabic text-xl sm:text-2xl font-bold" style={{ color: 'var(--ink)' }}>
            {book.title}
          </h1>
          <p className="font-arabic text-sm mt-1" style={{ color: 'var(--ink-faint)' }}>
            {page?.printed_page ? `الصفحة ${page.printed_page}` : `المقطع ${seq}`}
          </p>
          <div className="ornament mt-4 max-w-xs mx-auto">
            <span style={{ color: 'var(--gold)' }} className="text-xs">
              ❁
            </span>
          </div>
        </div>

        {loading ? (
          <div className="textblock space-y-4">
            {Array.from({ length: 10 }).map((_, i) => (
              <div
                key={i}
                className="h-4 rounded shimmer"
                style={{ width: `${68 + ((i * 37) % 30)}%`, marginInlineStart: 'auto' }}
              />
            ))}
          </div>
        ) : error ? (
          <p className="textblock text-center" style={{ color: 'var(--rubric)' }}>
            تعذّر تحميل الصفحة: {error}
          </p>
        ) : (
          <PageText text={page?.text} match={match} />
        )}

        <nav className="flex items-center justify-between gap-3 mt-12 pt-5 border-t" style={{ borderColor: 'var(--paper-edge)' }}>
          <NavButton onClick={() => go(seq + 1)} disabled={seq >= total} title="الصفحة التالية (←)">
            ‹ التالية
          </NavButton>
          <PageJump seq={seq} total={total} onGo={go} />
          <NavButton onClick={() => go(seq - 1)} disabled={seq <= 1} title="الصفحة السابقة (→)">
            السابقة ›
          </NavButton>
        </nav>

        <p className="text-center mt-4 font-ui text-[0.65rem]" style={{ color: 'var(--ink-faint)' }}>
          ← → لتقليب الصفحات · / للبحث
        </p>
      </article>
    </div>
  )
}
