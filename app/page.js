import Header from "@/components/Header";
import Footer from "@/components/Footer";
import VideoCard from "@/components/VideoCard";
import { getVideos, PAYPAL_HANDLE } from "@/lib/data";

// Der Katalog wird aus der Datenbank geladen und kann sich jederzeit über den
// Admin-Bereich ändern — deshalb kein statisches Prerendering/Caching.
export const dynamic = "force-dynamic";

export default async function HomePage() {
  const videos = await getVideos();

  return (
    <div className="min-h-screen bg-ink">
      <Header />

      <main>
        {/* Hero */}
        <section className="grain-overlay relative overflow-hidden border-b border-hairline">
          <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 sm:py-28">
            <p className="mb-5 font-mono text-xs uppercase tracking-[0.25em] text-brass">
              Private Catalog &middot; N&deg; 001&ndash;{String(videos.length).padStart(3, "0")}
            </p>
            <h1 className="max-w-3xl font-display text-4xl font-medium leading-[1.1] text-porcelain sm:text-6xl">
              Ein Archiv,{" "}
              <span className="italic text-brass-soft">kein Feed.</span>
            </h1>
            <p className="mt-6 max-w-xl text-base leading-relaxed text-stone sm:text-lg">
              Handverlesene Videos, einzeln nummeriert und einzeln bestellt.
              Keine Abos, kein Algorithmus &mdash; jede Bestellung wird
              persönlich geprüft und von Hand verschickt.
            </p>
            <a
              href="#katalog"
              className="mt-10 inline-flex items-center gap-2 rounded-full border border-brass/50 bg-brass/10 px-6 py-3 font-mono text-xs uppercase tracking-widest text-brass-soft transition-colors hover:bg-brass/20"
            >
              Katalog ansehen ↓
            </a>
          </div>
        </section>

        {/* Katalog */}
        <section id="katalog" className="mx-auto max-w-6xl px-5 py-16 sm:px-8 sm:py-24">
          <div className="mb-10 flex items-end justify-between border-b border-hairline pb-6">
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.25em] text-brass">
                Katalog
              </p>
              <h2 className="mt-2 font-display text-2xl text-porcelain sm:text-3xl">
                Aktuell verfügbar
              </h2>
            </div>
            <p className="hidden font-mono text-xs text-stone sm:block">
              {videos.length} Titel
            </p>
          </div>

          {videos.length === 0 ? (
            <div className="rounded-lg border border-dashed border-hairline p-12 text-center text-stone">
              Noch keine Videos im Katalog. Füge über den Admin-Bereich das
              erste Video hinzu.
            </div>
          ) : (
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {videos.map((video, index) => (
                <VideoCard key={video.id} video={video} index={index} />
              ))}
            </div>
          )}
        </section>

        {/* So funktioniert's */}
        <section
          id="so-funktionierts"
          className="border-t border-hairline bg-ink-soft"
        >
          <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 sm:py-24">
            <p className="font-mono text-xs uppercase tracking-[0.25em] text-brass">
              Ablauf
            </p>
            <h2 className="mt-2 max-w-lg font-display text-2xl text-porcelain sm:text-3xl">
              So funktioniert&rsquo;s
            </h2>
            <div className="mt-10 grid gap-8 sm:grid-cols-3">
              {[
                {
                  n: "01",
                  title: "Video auswählen",
                  text: "Öffne einen Titel aus dem Katalog. Dort steht der exakte Preis.",
                },
                {
                  n: "02",
                  title: "Per PayPal senden",
                  text: `Sende den genauen Betrag an paypal.me/${PAYPAL_HANDLE} und hinterlasse Email oder Telegram.`,
                },
                {
                  n: "03",
                  title: "Video erhalten",
                  text: "Nach manueller Prüfung wird dir das Video direkt zugeschickt. Das kann etwas dauern.",
                },
              ].map((step) => (
                <div key={step.n}>
                  <p className="font-mono text-3xl text-brass/70">{step.n}</p>
                  <h3 className="mt-3 font-display text-lg text-porcelain">
                    {step.title}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-stone">
                    {step.text}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}
