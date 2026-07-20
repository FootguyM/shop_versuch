import Link from "next/link";

export default function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-hairline/80 bg-ink/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
        <Link href="/" className="group flex items-baseline gap-2">
          <span className="font-display text-xl font-semibold tracking-tight text-porcelain sm:text-2xl">
            REEL<span className="text-brass">ROOM</span>
          </span>
          <span className="hidden font-mono text-[11px] uppercase tracking-[0.2em] text-stone sm:inline">
            private catalog
          </span>
        </Link>
        <nav className="flex items-center gap-6 font-mono text-xs uppercase tracking-widest text-stone">
          <a
            href="#katalog"
            className="transition-colors hover:text-brass"
          >
            Katalog
          </a>
          <a
            href="#so-funktionierts"
            className="hidden transition-colors hover:text-brass sm:inline"
          >
            So funktioniert&rsquo;s
          </a>
        </nav>
      </div>
    </header>
  );
}
