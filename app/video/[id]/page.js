import Link from "next/link";
import { notFound } from "next/navigation";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import PurchaseForm from "@/components/PurchaseForm";
import { getVideoById, formatPrice, buildPaypalLink } from "@/lib/data";

// Videodaten (Preis, Beschreibung, ...) können sich über den Admin-Bereich
// jederzeit ändern — deshalb kein statisches Prerendering/Caching.
export const dynamic = "force-dynamic";

export async function generateMetadata({ params }) {
  const { id } = await params;
  const video = await getVideoById(id);
  if (!video) return { title: "Video nicht gefunden — Reelroom" };
  return {
    title: `${video.title} — Reelroom`,
    description: video.description,
  };
}

export default async function VideoDetailPage({ params }) {
  const { id } = await params;
  const video = await getVideoById(id);

  if (!video) notFound();

  const priceLabel = formatPrice(video.price);
  const paypalLink = buildPaypalLink(video.price);

  return (
    <div className="min-h-screen bg-ink">
      <Header />

      <main className="mx-auto max-w-5xl px-5 py-12 sm:px-8 sm:py-16">
        <Link
          href="/"
          className="mb-8 inline-flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-stone transition-colors hover:text-brass"
        >
          ← Zurück zum Katalog
        </Link>

        <div className="grid gap-10 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <div className="overflow-hidden rounded-lg border border-hairline bg-ink-soft">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={video.thumbnail}
                alt={video.title}
                className="aspect-[3/2] w-full object-cover"
              />
            </div>

            <div className="mt-8 hidden lg:block">
              <PurchaseForm
                video={video}
                paypalLink={paypalLink}
                priceLabel={priceLabel}
              />
            </div>
          </div>

          <div className="lg:col-span-2">
            <h1 className="font-display text-2xl leading-snug text-porcelain sm:text-3xl">
              {video.title}
            </h1>
            <p className="mt-3 font-mono text-lg text-brass">{priceLabel}</p>
            <p className="mt-4 text-sm leading-relaxed text-stone">
              {video.description}
            </p>

            <div className="mt-8 lg:hidden">
              <PurchaseForm
                video={video}
                paypalLink={paypalLink}
                priceLabel={priceLabel}
              />
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
