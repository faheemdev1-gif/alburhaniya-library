import { useState } from 'react'

/**
 * The backend already returns an escaped, `<mark>`-highlighted window around
 * the hit. The one thing it cannot know is that a `***` inside that window is
 * the seam of a bayt — so turn it into the rosette the reader will meet again
 * on the page itself.
 */
function snippetHtml(html) {
  return String(html || '').replace(
    /(?<!\*)\*{3}(?!\*)/g,
    ' <span class="bayt__rosette">۞</span> '
  )
}

function GradeChip({ code, grade }) {
  const primary = code === 'primary'
  return (
    <span
      className="font-ui text-[0.6rem] px-1.5 py-0.5 rounded whitespace-nowrap"
      style={{
        color: primary ? 'var(--rubric)' : 'var(--ink-faint)',
        background: primary ? 'color-mix(in srgb, var(--rubric) 10%, transparent)' : 'var(--paper-sunk)',
      }}
      title={primary ? 'من كلام الشيخ نفسه' : 'شرح أو نقل عن الشيخ'}
    >
      {grade}
    </span>
  )
}

export function ResultCard({ result, onOpen, showBook = true, compact = false }) {
  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onOpen(result)}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onOpen(result))}
      className={`card cursor-pointer transition-all fade-in ${compact ? 'p-3' : 'p-4'}`}
    >
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <div className="flex items-center gap-2 min-w-0">
          {showBook && (
            <span className="font-arabic text-sm font-semibold truncate" style={{ color: 'var(--ink)' }}>
              {result.book_title}
            </span>
          )}
          {showBook && <GradeChip code={result.source_code} grade={result.source_grade} />}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="font-ui text-[0.65rem]" style={{ color: 'var(--ink-faint)' }}>
            {result.occurrences}×
          </span>
          <span
            className="font-arabic text-xs px-2 py-0.5 rounded"
            style={{ background: 'var(--paper-sunk)', color: 'var(--ink-muted)' }}
          >
            {result.page_label}
          </span>
        </div>
      </div>

      <p
        className="font-arabic text-sm leading-loose"
        style={{ color: 'var(--ink-muted)' }}
        dir="rtl"
        dangerouslySetInnerHTML={{ __html: snippetHtml(result.snippet) }}
      />
    </article>
  )
}

const PAGE_SIZE = 40

/** Library-wide results, grouped by the book they came from. */
export default function SearchResults({ results, query, loading, error, onOpen, onClearSearch }) {
  const [shown, setShown] = useState(PAGE_SIZE)

  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="card p-4 space-y-2">
            <div className="h-4 w-48 shimmer rounded" />
            <div className="h-3 w-full shimmer rounded" />
            <div className="h-3 w-4/6 shimmer rounded" />
          </div>
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div
        className="card p-4 font-arabic text-sm"
        style={{ color: 'var(--rubric)', borderColor: 'var(--rubric)' }}
      >
        تعذّر إتمام البحث: {error}
      </div>
    )
  }

  if (!results.length) {
    return (
      <div className="text-center py-16">
        <p className="font-arabic text-lg" style={{ color: 'var(--ink)' }}>
          لا توجد صفحة ورد فيها «{query}»
        </p>
        <p className="font-arabic text-sm mt-2" style={{ color: 'var(--ink-faint)' }}>
          البحث يطابق الكلمة كما كُتبت، مع تجاهل التشكيل. جرّب صيغة أخرى للكلمة.
        </p>
        <button
          onClick={onClearSearch}
          className="mt-5 font-arabic text-sm underline underline-offset-4"
          style={{ color: 'var(--gold)' }}
        >
          العودة إلى فهرس الكتب
        </button>
      </div>
    )
  }

  const bookCount = new Set(results.map((r) => r.book_id)).size
  const visible = results.slice(0, shown)

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 mb-5">
        <p className="font-arabic text-sm" style={{ color: 'var(--ink-muted)' }}>
          <span style={{ color: 'var(--rubric)' }}>{results.length}</span> صفحة في{' '}
          <span style={{ color: 'var(--rubric)' }}>{bookCount}</span> كتاباً
        </p>
        <button
          onClick={onClearSearch}
          className="font-arabic text-xs underline underline-offset-4 shrink-0"
          style={{ color: 'var(--ink-faint)' }}
        >
          فهرس الكتب
        </button>
      </div>

      <div className="space-y-2.5">
        {visible.map((r) => (
          <ResultCard key={`${r.book_id}-${r.seq}`} result={r} onOpen={onOpen} />
        ))}
      </div>

      {shown < results.length && (
        <button
          onClick={() => setShown((n) => n + PAGE_SIZE * 2)}
          className="w-full mt-4 py-3 rounded card font-arabic text-sm transition-colors"
          style={{ color: 'var(--ink-muted)' }}
        >
          عرض المزيد — بقي {results.length - shown} صفحة
        </button>
      )}
    </div>
  )
}
