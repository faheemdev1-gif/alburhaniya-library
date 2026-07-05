import { useState } from 'react'

export default function SearchBar({ onSearch, loading, selectedCount, totalBooks }) {
  const [value, setValue] = useState('')

  const submit = () => {
    if (value.trim()) onSearch(value.trim())
  }

  return (
    <div className="relative">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={value}
            onChange={e => setValue(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && submit()}
            placeholder="ابحث في الكتب العربية…"
            className="search-input w-full bg-white border border-gold/30 rounded px-4 py-3 pr-10 text-ink placeholder-ink/30 focus:outline-none focus:border-gold focus:ring-1 focus:ring-gold/30 transition-colors shadow-sm"
            autoFocus
          />
          {/* Search icon */}
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gold/50 pointer-events-none">
            ◎
          </span>
        </div>

        <button
          onClick={submit}
          disabled={loading || !value.trim()}
          className="bg-gold hover:bg-gold-light disabled:opacity-40 disabled:cursor-not-allowed text-ink font-arabic font-semibold px-6 py-3 rounded transition-colors shadow-sm whitespace-nowrap"
        >
          {loading ? '…' : 'بحث'}
        </button>
      </div>

      {/* Scope indicator */}
      <p className="font-ui text-xs text-ink/40 mt-1.5 text-left">
        {selectedCount === totalBooks || selectedCount === 0
          ? `البحث في ${totalBooks} كتاب`
          : `البحث في ${selectedCount} كتاب من أصل ${totalBooks}`}
      </p>
    </div>
  )
}
