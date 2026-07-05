import ResultCard from './ResultCard'

function Skeleton() {
  return (
    <div className="bg-white border border-gold/10 rounded p-4 space-y-2">
      <div className="flex justify-between">
        <div className="h-4 w-40 shimmer rounded" />
        <div className="h-4 w-12 shimmer rounded" />
      </div>
      <div className="h-3 w-full shimmer rounded" />
      <div className="h-3 w-5/6 shimmer rounded" />
      <div className="h-3 w-4/6 shimmer rounded" />
    </div>
  )
}

export default function ResultsPanel({ results, loading, searched, query, onOpen }) {
  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} />)}
      </div>
    )
  }

  if (!searched) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-ink/30">
        <div className="text-5xl mb-4 select-none">🔎</div>
        <p className="font-arabic text-base">ابحث عن أي كلمة في الكتب</p>
        <p className="font-ui text-xs mt-1">ستظهر كل صفحة وردت فيها الكلمة، مع تمييزها</p>
      </div>
    )
  }

  if (results.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-ink/40">
        <div className="text-4xl mb-4 select-none">🕯</div>
        <p className="font-arabic text-base">لم يُعثر على نتائج</p>
        <p className="font-ui text-xs mt-1 text-ink/30">جرّب كلمات أخرى أو وسّع نطاق البحث</p>
      </div>
    )
  }

  return (
    <div>
      {/* Summary bar */}
      <div className="flex items-center justify-between mb-4">
        <div className="ornament text-sm">
          <span className="font-arabic text-ink/50">{results.length} نتيجة</span>
        </div>
        <p className="font-arabic text-xs text-ink/40 mr-2">
          نتائج البحث عن: <span className="text-gold font-semibold">"{query}"</span>
        </p>
      </div>

      <div className="space-y-3">
        {results.map((r, i) => (
          <ResultCard key={`${r.chunk_id}-${i}`} result={r} onOpen={onOpen} />
        ))}
      </div>
    </div>
  )
}
