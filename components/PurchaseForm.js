"use client";

import { useState } from "react";
import CopyButton from "./CopyButton";
import { PAYPAL_HANDLE } from "@/lib/data";

export default function PurchaseForm({ video, paypalLink, priceLabel }) {
  const [contact, setContact] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!contact.trim()) {
      setError("Bitte gib deine Email-Adresse oder deinen Telegram-Namen an.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch("/api/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          videoId: video.id,
          videoTitle: video.title,
          price: video.price,
          contact: contact.trim(),
        }),
      });
      if (!res.ok) throw new Error("request-failed");
      setSubmitted(true);
    } catch {
      setError(
        "Das hat leider nicht geklappt. Bitte versuch es gleich noch einmal."
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <div className="rounded-lg border border-brass/40 bg-brass/10 p-6">
        <p className="font-mono text-xs uppercase tracking-widest text-brass">
          Eingegangen ✓
        </p>
        <h3 className="mt-2 font-display text-xl text-porcelain">
          Danke, wir haben deine Angaben erhalten.
        </h3>
        <p className="mt-2 text-sm leading-relaxed text-stone">
          Sobald deine Zahlung geprüft ist, senden wir{" "}
          <span className="text-porcelain">&bdquo;{video.title}&ldquo;</span>{" "}
          an <span className="text-porcelain">{contact}</span>. Der Versand
          erfolgt manuell &mdash; das kann etwas dauern.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-hairline bg-panel">
      <div className="border-b border-hairline p-6">
        <p className="font-mono text-xs uppercase tracking-widest text-brass">
          So bekommst du dieses Video
        </p>
      </div>

      <div className="grid gap-6 p-6 sm:grid-cols-3">
        <div>
          <p className="font-mono text-2xl text-brass/70">01</p>
          <h4 className="mt-2 font-display text-base text-porcelain">
            Betrag senden
          </h4>
          <p className="mt-1 text-sm text-stone">
            Sende genau{" "}
            <span className="font-mono text-brass-soft">{priceLabel}</span>{" "}
            per PayPal an{" "}
            <span className="text-porcelain">paypal.me/{PAYPAL_HANDLE}</span>.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <a
              href={paypalLink}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center rounded-full bg-brass px-4 py-2 font-mono text-[11px] uppercase tracking-widest text-ink transition-colors hover:bg-brass-soft"
            >
              In PayPal öffnen ↗
            </a>
            <CopyButton value={priceLabel} label="Betrag kopieren" />
          </div>
        </div>

        <div>
          <p className="font-mono text-2xl text-brass/70">02</p>
          <h4 className="mt-2 font-display text-base text-porcelain">
            Kontakt angeben
          </h4>
          <p className="mt-1 text-sm text-stone">
            Trag deine Email-Adresse oder deinen Telegram-Nutzernamen ein,
            damit wir dir das Video zustellen können.
          </p>
        </div>

        <div>
          <p className="font-mono text-2xl text-brass/70">03</p>
          <h4 className="mt-2 font-display text-base text-porcelain">
            Video erhalten
          </h4>
          <p className="mt-1 text-sm text-stone">
            Nach Zahlungseingang prüfen wir manuell und schicken dir das
            Video zu.
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="border-t border-hairline p-6">
        <label
          htmlFor="contact"
          className="mb-2 block font-mono text-xs uppercase tracking-widest text-stone"
        >
          Email oder Telegram-Nutzername
        </label>
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            id="contact"
            type="text"
            value={contact}
            onChange={(e) => setContact(e.target.value)}
            placeholder="name@email.de oder @telegramname"
            className="w-full rounded-md border border-hairline bg-ink px-4 py-3 text-sm text-porcelain placeholder:text-stone/60 focus:border-brass focus:outline-none focus:ring-1 focus:ring-brass"
          />
          <button
            type="submit"
            disabled={submitting}
            className="whitespace-nowrap rounded-md bg-brass px-6 py-3 font-mono text-xs uppercase tracking-widest text-ink transition-colors hover:bg-brass-soft disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? "Wird gesendet…" : "Zahlung gemeldet"}
          </button>
        </div>
        {error && (
          <p className="mt-2 text-sm text-red-400">{error}</p>
        )}
        <p className="mt-4 flex items-start gap-2 text-xs leading-relaxed text-stone">
          <span aria-hidden>⏳</span>
          <span>
            Hinweis: Videos werden manuell geprüft und verschickt. Das kann
            etwas dauern &mdash; du bekommst dein Video garantiert, sobald die
            Zahlung bestätigt ist.
          </span>
        </p>
      </form>
    </div>
  );
}
