import clsx from 'clsx'

// Exact-match search: show how many times the word appears on this page
// rather than a semantic "similarity %" (which no longer applies).
function OccurrenceBadge({ occurrences }) {
  if (!occurrences) return null
  const color = occurrences > 5 ? 'bg-sage/20 text-sage' : occurrences > 1 ? 'bg-gold/20 text-gold-dark' : 'bg-parch-dark text-ink/40'
  return (
    <span className={clsx('font-ui text-xs px-1.5 py-0.5 rounded', color)}>
      {occurrences}×
    </span>
  )
}

export default function ResultCard({ result, onOpen }) {
  return (
    <article
      className="group bg-white border border-gold/20 rounded p-4 hover:border-gold/50 hover:shadow-md transition-all cursor-pointer fade-in"
      onClick={() => onOpen(result)}
    >
      {/* Book + page */}
      <div className="flex items-center justify-between mb-2 gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-gold text-base flex-shrink-0">📖</span>
          <span className="font-arabic font-semibold text-sm text-ink truncate">
            {result.book_title}
          </span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <OccurrenceBadge occurrences={result.occurrences} />
          <span className="font-ui text-xs bg-parch-dark text-ink/60 px-2 py-0.5 rounded">
            ص {result.page_label || result.page_number}
          </span>
        </div>
      </div>

      {/* Text snippet */}
      <p
        className="font-arabic text-sm leading-relaxed text-ink/80 line-clamp-4 text-right"
        dir="rtl"
        dangerouslySetInnerHTML={{ __html: result.highlight || result.text }}
      />

      {/* CTA */}
      <div className="mt-3 flex items-center justify-between">
        <span className="font-ui text-xs text-gold opacity-0 group-hover:opacity-100 transition-opacity">
          اضغط لقراءة النص كاملاً ←
        </span>
      </div>
    </article>
  )
}
