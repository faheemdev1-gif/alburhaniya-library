import SearchBar from './SearchBar'

function IconButton({ label, onClick, children, disabled }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className="w-8 h-8 flex items-center justify-center rounded transition-colors disabled:opacity-30"
      style={{ color: 'var(--ink-muted)' }}
      onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--paper-sunk)')}
      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
    >
      {children}
    </button>
  )
}

/**
 * Sticky across both screens, so the search field is always in the same
 * place. In the reader the brand collapses to a back arrow and the open
 * book's title, and the search scope narrows to that book.
 */
export default function Header({
  book,
  onBack,
  search,
  theme,
  onToggleTheme,
  onZoom,
  canZoomIn,
  canZoomOut,
}) {
  return (
    <header
      className="app-header sticky top-0 z-40 border-b backdrop-blur"
      style={{ borderColor: 'var(--paper-edge)' }}
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-3 flex items-center gap-3 sm:gap-5">
        {book ? (
          <button
            onClick={onBack}
            className="flex items-center gap-2 min-w-0 max-w-[9rem] sm:max-w-xs shrink-0 text-right transition-opacity hover:opacity-70"
            title="رجوع إلى المكتبة"
          >
            <span style={{ color: 'var(--gold)' }} aria-hidden="true">
              ›
            </span>
            <span className="min-w-0">
              <span
                className="block font-arabic text-sm font-semibold truncate"
                style={{ color: 'var(--ink)' }}
              >
                {book.title}
              </span>
              <span className="block font-ui text-[0.65rem]" style={{ color: 'var(--ink-faint)' }}>
                رجوع إلى المكتبة
              </span>
            </span>
          </button>
        ) : (
          <div className="flex items-center gap-2.5 shrink-0">
            <span style={{ color: 'var(--gold)' }} className="text-2xl select-none" aria-hidden="true">
              ❁
            </span>
            <span className="min-w-0">
              <span
                className="block font-arabic text-base font-bold leading-tight"
                style={{ color: 'var(--ink)' }}
              >
                المكتبة البرهانية
              </span>
              <span
                className="hidden sm:block font-ui text-[0.6rem] tracking-[0.18em] uppercase"
                style={{ color: 'var(--ink-faint)' }}
              >
                Burhaniya Library
              </span>
            </span>
          </div>
        )}

        <div className="flex-1 min-w-0">
          <SearchBar {...search} />
        </div>

        <div className="hidden sm:flex items-center gap-0.5 shrink-0">
          <IconButton label="تصغير الخط" onClick={() => onZoom(-1)} disabled={!canZoomOut}>
            <span className="text-xs font-ui">A−</span>
          </IconButton>
          <IconButton label="تكبير الخط" onClick={() => onZoom(1)} disabled={!canZoomIn}>
            <span className="text-base font-ui">A+</span>
          </IconButton>
          <IconButton
            label={theme === 'night' ? 'وضع النهار' : 'وضع الليل'}
            onClick={onToggleTheme}
          >
            <span aria-hidden="true">{theme === 'night' ? '☀' : '☾'}</span>
          </IconButton>
        </div>
      </div>
    </header>
  )
}
