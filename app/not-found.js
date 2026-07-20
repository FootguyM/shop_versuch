import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-ink px-6 text-center">
      <p className="font-mono text-xs uppercase tracking-[0.25em] text-brass">
        N&deg; 404
      </p>
      <h1 className="mt-4 font-display text-3xl text-porcelain">
        Dieser Titel ist nicht im Katalog.
      </h1>
      <p className="mt-3 max-w-sm text-sm text-stone">
        Vielleicht wurde er entfernt oder der Link ist nicht mehr aktuell.
      </p>
      <Link
        href="/"
        className="mt-8 inline-flex items-center gap-2 rounded-full border border-brass/50 bg-brass/10 px-6 py-3 font-mono text-xs uppercase tracking-widest text-brass-soft transition-colors hover:bg-brass/20"
      >
        Zurück zum Katalog
      </Link>
    </div>
  );
}
