export default function Header() {
  return (
    <header className="border-b border-gold/30 bg-ink text-parch">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        {/* Logo / title */}
        <div className="flex items-center gap-3">
          <span className="text-gold text-3xl select-none">☽</span>
          <div>
            <h1 className="font-arabic text-xl font-bold leading-tight text-parch">
              المكتبة العربية
            </h1>
            <p className="font-ui text-xs text-parch/50 tracking-widest uppercase">
              Arabic Library Search
            </p>
          </div>
        </div>

        {/* Decorative kufic band */}
        <div className="hidden md:flex items-center gap-1 text-gold/40 text-lg select-none">
          {'◆ ◇ ◆ ◇ ◆'.split(' ').map((c, i) => (
            <span key={i}>{c}</span>
          ))}
        </div>
      </div>
    </header>
  )
}
