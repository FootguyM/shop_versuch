import Link from "next/link";
import { formatPrice } from "@/lib/data";

export default function VideoCard({ video, index }) {
  const catalogNumber = String(index + 1).padStart(2, "0");

  return (
    <Link
      href={`/video/${video.id}`}
      className="group block overflow-hidden rounded-lg border border-hairline bg-panel transition-all duration-300 hover:-translate-y-1 hover:border-brass/60 hover:shadow-[0_0_0_1px_rgba(201,162,75,0.25),0_20px_40px_-20px_rgba(0,0,0,0.6)]"
    >
      <div className="relative aspect-[3/2] overflow-hidden bg-ink-soft">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={video.thumbnail}
          alt={video.title}
          loading="lazy"
          className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
        />
        <div className="absolute left-3 top-3 rounded-full border border-hairline bg-ink/80 px-2.5 py-1 font-mono text-[11px] tracking-widest text-brass-soft backdrop-blur">
          N&deg; {catalogNumber}
        </div>
      </div>

      <div className="ticket-perforation flex flex-col gap-2 p-5">
        <h3 className="font-display text-lg leading-snug text-porcelain">
          {video.title}
        </h3>
        <p className="text-sm leading-relaxed text-stone">
          {video.description}
        </p>
        <div className="mt-2 flex items-center justify-between border-t border-dashed border-hairline pt-3">
          <span className="font-mono text-sm text-brass">
            {formatPrice(video.price)}
          </span>
          <span className="font-mono text-[11px] uppercase tracking-widest text-stone transition-colors group-hover:text-brass">
            Ansehen →
          </span>
        </div>
      </div>
    </Link>
  );
}
