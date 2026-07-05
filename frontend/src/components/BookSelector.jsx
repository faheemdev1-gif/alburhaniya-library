import { useState } from 'react'
import clsx from 'clsx'

function BookRow({ book, selected, onToggle, onDelete }) {
  const [confirming, setConfirming] = useState(false)

  return (
    <div
      className={clsx(
        'group flex items-start gap-2 p-2 rounded cursor-pointer transition-colors',
        selected ? 'bg-gold/15 border border-gold/40' : 'hover:bg-parch-dark border border-transparent'
      )}
      onClick={() => onToggle(book.book_id)}
    >
      {/* Checkbox */}
      <div className={clsx(
        'mt-0.5 w-4 h-4 flex-shrink-0 rounded border transition-colors',
        selected ? 'bg-gold border-gold' : 'border-gold/40'
      )}>
        {selected && (
          <svg viewBox="0 0 10 10" className="w-4 h-4 text-ink p-0.5">
            <path d="M1.5 5L4 7.5L8.5 2.5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round"/>
          </svg>
        )}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className="font-arabic text-sm leading-snug truncate">{book.title}</p>
        <p className="font-ui text-xs text-ink/40 mt-0.5">
          {book.pages ?? '—'} صفحة · {book.chunks ?? '—'} مقطع
        </p>
      </div>

      {/* Delete */}
      <button
        onClick={e => { e.stopPropagation(); setConfirming(true) }}
        className="opacity-0 group-hover:opacity-100 text-rust/60 hover:text-rust text-xs px-1 transition-opacity"
        title="حذف"
      >
        ✕
      </button>

      {/* Confirm overlay */}
      {confirming && (
        <div
          className="absolute inset-0 bg-parch/95 flex items-center justify-center gap-2 rounded z-10"
          onClick={e => e.stopPropagation()}
        >
          <span className="font-arabic text-xs text-ink/70">حذف الكتاب؟</span>
          <button
            onClick={() => { onDelete(book.book_id); setConfirming(false) }}
            className="bg-rust text-parch text-xs px-2 py-1 rounded"
          >نعم</button>
          <button
            onClick={() => setConfirming(false)}
            className="text-ink/50 text-xs px-2 py-1"
          >لا</button>
        </div>
      )}
    </div>
  )
}

export default function BookSelector({ books, loading, ingesting, selectedIds, onToggle, onSelectAll, onClearAll, onIngestAll, onUpload, onDelete }) {
  const allSelected = books.length > 0 && selectedIds.length === books.length
  const someSelected = selectedIds.length > 0 && !allSelected

  return (
    <aside className="w-72 flex-shrink-0 flex flex-col gap-4">
      {/* Header */}
      <div>
        <h2 className="font-arabic text-base font-semibold text-ink mb-1">الكتب</h2>
        <div className="flex items-center gap-3 text-xs font-ui text-ink/50">
          <button onClick={onSelectAll} className="hover:text-gold transition-colors">تحديد الكل</button>
          <span>·</span>
          <button onClick={onClearAll} className="hover:text-gold transition-colors">إلغاء التحديد</button>
          <span className="mr-auto">{selectedIds.length}/{books.length}</span>
        </div>
      </div>

      {/* Book list */}
      <div className="flex-1 overflow-y-auto space-y-1 max-h-[60vh] pl-1">
        {loading ? (
          Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-12 rounded shimmer" />
          ))
        ) : books.length === 0 ? (
          <div className="text-center py-8 text-ink/40">
            <p className="font-arabic text-sm">لا توجد كتب بعد</p>
            <p className="font-ui text-xs mt-1">ابدأ بالفهرسة أدناه</p>
          </div>
        ) : (
          books.map(book => (
            <div key={book.book_id} className="relative">
              <BookRow
                book={book}
                selected={selectedIds.includes(book.book_id)}
                onToggle={onToggle}
                onDelete={onDelete}
              />
            </div>
          ))
        )}
      </div>

      {/* Actions */}
      <div className="border-t border-gold/20 pt-3 space-y-2">
        <button
          onClick={onIngestAll}
          disabled={ingesting}
          className={clsx(
            'w-full font-arabic text-sm py-2 px-3 rounded border transition-colors',
            ingesting
              ? 'border-gold/20 text-ink/30 cursor-not-allowed'
              : 'border-gold/40 text-gold hover:bg-gold/10'
          )}
        >
          {ingesting ? '⏳ جارٍ الفهرسة…' : '⟳ فهرسة جميع الكتب'}
        </button>

        <label className="w-full flex items-center justify-center gap-2 font-arabic text-sm py-2 px-3 rounded border border-dashed border-gold/30 text-ink/50 hover:border-gold/60 hover:text-gold cursor-pointer transition-colors">
          <span>↑ رفع كتاب</span>
          <input
            type="file"
            accept=".pdf,.docx,.doc,.html,.htm,.txt"
            className="hidden"
            onChange={e => e.target.files[0] && onUpload(e.target.files[0])}
          />
        </label>
      </div>
    </aside>
  )
}
