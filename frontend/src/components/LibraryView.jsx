function BookCard({ book, onOpen }) {
  return (
    <button
      onClick={() => onOpen(book)}
      className="card p-4 text-right transition-all hover:shadow-sm w-full h-full flex flex-col gap-2 group"
    >
      <span
        className="font-arabic text-[0.95rem] leading-snug font-semibold"
        style={{ color: 'var(--ink)' }}
      >
        {book.title}
      </span>
      <span
        className="font-ui text-xs mt-auto pt-1 flex items-center gap-2"
        style={{ color: 'var(--ink-faint)' }}
      >
        {book.page_count} صفحة
        <span
          className="opacity-0 group-hover:opacity-100 transition-opacity font-arabic"
          style={{ color: 'var(--gold)' }}
        >
          افتح الكتاب ←
        </span>
      </span>
    </button>
  )
}

function Section({ title, note, books, onOpen }) {
  if (!books.length) return null
  return (
    <section className="mb-12">
      <div className="flex items-baseline gap-3 mb-1">
        <h2 className="font-arabic text-lg font-bold" style={{ color: 'var(--rubric)' }}>
          {title}
        </h2>
        <span className="font-ui text-xs" style={{ color: 'var(--ink-faint)' }}>
          {books.length}
        </span>
        <span className="flex-1 h-px" style={{ background: 'var(--paper-edge)' }} />
      </div>
      <p className="font-arabic text-sm mb-5" style={{ color: 'var(--ink-muted)' }}>
        {note}
      </p>
      <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {books.map((b) => (
          <BookCard key={b.book_id} book={b} onOpen={onOpen} />
        ))}
      </div>
    </section>
  )
}

/**
 * The library index. Books are grouped by provenance, because that is the
 * distinction a reader of this collection actually needs before they start
 * quoting: whether they are reading the shaykh or reading about him.
 */
export default function LibraryView({ books, loading, error, onOpen }) {
  if (loading) {
    return (
      <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 9 }).map((_, i) => (
          <div key={i} className="h-24 rounded shimmer" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="card p-5 font-arabic text-sm" style={{ color: 'var(--rubric)' }}>
        تعذّر تحميل فهرس الكتب: {error}
        <span className="block mt-1" style={{ color: 'var(--ink-faint)' }}>
          إن كان الخادم في وضع السكون فقد يستغرق أول طلب دقيقة تقريباً. أعد المحاولة.
        </span>
      </div>
    )
  }

  const primary = books.filter((b) => b.source_code === 'primary')
  const secondary = books.filter((b) => b.source_code !== 'primary')
  const pages = books.reduce((n, b) => n + (b.page_count || 0), 0)

  return (
    <div>
      <div className="mb-10">
        <p className="font-arabic text-base leading-loose max-w-2xl" style={{ color: 'var(--ink-muted)' }}>
          {books.length} كتاباً، {pages.toLocaleString('ar-EG')} صفحة، قابلة للبحث كلمةً بكلمة.
          ابحث من الأعلى في المكتبة كلها، أو افتح كتاباً ليصير البحث داخله وحده.
        </p>
      </div>

      <Section
        title="أصلي"
        note="من كلام الشيخ نفسه — ما يُنقل منه يُنسب إليه مباشرة."
        books={primary}
        onOpen={onOpen}
      />
      <Section
        title="ثانوي"
        note="شروح وتلخيصات ونقول عن الشيخ — يُنسب القول فيها إلى ناقله."
        books={secondary}
        onOpen={onOpen}
      />
    </div>
  )
}
