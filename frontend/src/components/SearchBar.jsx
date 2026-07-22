import { useEffect, useRef, useState } from 'react'

/**
 * The one search field in the app. It never moves — only its scope changes:
 * on the library screen it searches every book, and once a book is open it
 * searches inside that book. The scope is spelled out on the field itself so
 * the reader never has to guess which one they are about to get.
 */
export default function SearchBar({
  scopeLabel,
  placeholder,
  loading,
  value,
  onChange,
  onSubmit,
  onClear,
  onEscapeScope,
  escapeLabel,
  autoFocus = false,
}) {
  const [local, setLocal] = useState(value || '')
  const input = useRef(null)

  useEffect(() => {
    setLocal(value || '')
  }, [value])

  // `/` focuses the field from anywhere, the way a reader expects.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === '/' && document.activeElement !== input.current) {
        e.preventDefault()
        input.current?.focus()
        input.current?.select()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const submit = () => {
    const term = local.trim()
    if (term) onSubmit(term)
  }

  const clear = () => {
    setLocal('')
    onClear?.()
    input.current?.focus()
  }

  return (
    <div className="w-full">
      <div
        className="flex items-stretch gap-1 rounded-md border transition-colors focus-within:border-[var(--gold)]"
        style={{ background: 'var(--paper-raised)', borderColor: 'var(--paper-edge)' }}
      >
        <span
          className="hidden sm:flex items-center whitespace-nowrap px-3 text-xs font-ui border-l"
          style={{ color: 'var(--ink-muted)', borderColor: 'var(--paper-edge)' }}
          title="نطاق البحث"
        >
          {scopeLabel}
        </span>

        <input
          ref={input}
          type="search"
          value={local}
          onChange={(e) => {
            setLocal(e.target.value)
            onChange?.(e.target.value)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submit()
            if (e.key === 'Escape') clear()
          }}
          placeholder={placeholder}
          aria-label={scopeLabel}
          autoFocus={autoFocus}
          className="search-input flex-1 min-w-0 bg-transparent px-3 py-2.5 text-base focus:outline-none"
          style={{ color: 'var(--ink)' }}
        />

        {local && (
          <button
            onClick={clear}
            className="px-2 text-lg leading-none transition-colors hover:opacity-100 opacity-50"
            style={{ color: 'var(--ink-muted)' }}
            title="مسح (Esc)"
            aria-label="مسح البحث"
          >
            ×
          </button>
        )}

        <button
          onClick={submit}
          disabled={loading || !local.trim()}
          className="px-5 my-1 ml-1 rounded font-arabic text-sm font-semibold transition-opacity disabled:opacity-30 disabled:cursor-not-allowed"
          style={{ background: 'var(--gold)', color: '#211a11' }}
        >
          {loading ? '…' : 'بحث'}
        </button>
      </div>

      {onEscapeScope && (
        <button
          onClick={onEscapeScope}
          className="mt-1.5 font-ui text-xs underline underline-offset-2 transition-colors"
          style={{ color: 'var(--ink-faint)' }}
        >
          {escapeLabel}
        </button>
      )}
    </div>
  )
}
