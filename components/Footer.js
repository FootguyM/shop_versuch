export default function Footer() {
  return (
    <footer className="border-t border-hairline">
      <div className="mx-auto max-w-6xl px-5 py-10 sm:px-8">
        <div className="grid gap-8 sm:grid-cols-3">
          <div>
            <p className="font-display text-lg text-porcelain">
              REEL<span className="text-brass">ROOM</span>
            </p>
            <p className="mt-2 max-w-xs text-sm text-stone">
              Ein kleiner, direkt kuratierter Katalog. Jede Bestellung wird
              persönlich bearbeitet.
            </p>
          </div>
          <div className="font-mono text-xs uppercase tracking-widest text-stone">
            <p className="mb-3 text-porcelain/80">Zahlung</p>
            <p>Ausschließlich per PayPal</p>
            <p>Manuelle Prüfung &amp; Versand</p>
          </div>
          <div className="font-mono text-xs uppercase tracking-widest text-stone">
            <p className="mb-3 text-porcelain/80">Hinweis</p>
            <p>Digitale Inhalte, kein Abo</p>
            <p>Versand kann etwas dauern</p>
          </div>
        </div>
        <p className="mt-10 border-t border-hairline pt-6 text-xs text-stone/70">
          © {new Date().getFullYear()} Reelroom. Alle gezeigten Titel dienen
          als Beispiel-Katalog.
        </p>
      </div>
    </footer>
  );
}
