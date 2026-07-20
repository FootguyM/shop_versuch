"use client";

import { useState } from "react";

export default function CopyButton({ value, label = "Kopieren" }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard-Zugriff verweigert (z.B. sehr alter Browser) — kein Drama,
      // der Wert steht ohnehin sichtbar daneben.
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="rounded-full border border-hairline px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-stone transition-colors hover:border-brass/60 hover:text-brass"
    >
      {copied ? "Kopiert ✓" : label}
    </button>
  );
}
