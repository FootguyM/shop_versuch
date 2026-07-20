import { redis, hasRedis } from "./redis";

const VIDEOS_KEY = "reelroom:videos";
const ORDERS_KEY = "reelroom:orders";

// ---------------------------------------------------------------------------
// Beispiel-Katalog. Das ist nur Platzhalter-Content, damit die Seite von
// Anfang an gut aussieht — im Admin-Bereich kannst du jeden Eintrag
// bearbeiten, löschen oder eigene Videos hinzufügen.
// ---------------------------------------------------------------------------
export const SEED_VIDEOS = [
  {
    id: "v1",
    title: "Sonnenaufgang am Vulkan",
    description:
      "Exklusiver Reisefilm: eine ruhige Nachtwanderung endet im Farbenspiel des ersten Sonnenlichts über dem Kraterrand.",
    price: 12,
    thumbnail: "https://picsum.photos/seed/reelroom-v1/900/600",
    createdAt: "2026-01-04T10:00:00.000Z",
  },
  {
    id: "v2",
    title: "Studio Session — Behind the Scenes",
    description:
      "Unveröffentlichtes Material aus einer nächtlichen Studiosession. Roh, unbearbeitet, nah dran.",
    price: 9,
    thumbnail: "https://picsum.photos/seed/reelroom-v2/900/600",
    createdAt: "2026-01-10T10:00:00.000Z",
  },
  {
    id: "v3",
    title: "Tanz-Tutorial: Advanced Combo",
    description:
      "Schritt für Schritt erklärt: eine anspruchsvolle Choreografie in voller Länge, inklusive Zählzeiten.",
    price: 15,
    thumbnail: "https://picsum.photos/seed/reelroom-v3/900/600",
    createdAt: "2026-01-18T10:00:00.000Z",
  },
  {
    id: "v4",
    title: "Nachtfahrt durch Tokyo",
    description:
      "Eine einstündige Fahrt durch die beleuchteten Straßen von Shibuya und Shinjuku, in einem Schnitt.",
    price: 8,
    thumbnail: "https://picsum.photos/seed/reelroom-v4/900/600",
    createdAt: "2026-02-02T10:00:00.000Z",
  },
  {
    id: "v5",
    title: "Kochshow Spezial: Streetfood Bangkok",
    description:
      "Die besten Streetfood-Stände einer Nacht, mit Rezeptideen zum Nachkochen und Originalton.",
    price: 10,
    thumbnail: "https://picsum.photos/seed/reelroom-v5/900/600",
    createdAt: "2026-02-14T10:00:00.000Z",
  },
  {
    id: "v6",
    title: "Fitness Challenge: Full Body",
    description:
      "45 Minuten Ganzkörpertraining ohne Geräte, in voller Länge und ohne Schnitte mitgefilmt.",
    price: 14,
    thumbnail: "https://picsum.photos/seed/reelroom-v6/900/600",
    createdAt: "2026-02-20T10:00:00.000Z",
  },
];

// Fallback-Speicher für die lokale Entwicklung ohne angebundene Datenbank.
// Achtung: Auf Vercel läuft jede Anfrage potenziell in einer neuen,
// isolierten Funktionsinstanz — ohne Redis werden Änderungen dort NICHT
// zuverlässig gespeichert. Siehe README.md.
let memoryVideos = null;
let memoryOrders = [];

function parseOrArray(value, fallback) {
  if (!value) return fallback;
  if (typeof value === "string") {
    try {
      return JSON.parse(value);
    } catch {
      return fallback;
    }
  }
  return value;
}

export async function getVideos() {
  if (hasRedis) {
    const data = await redis.get(VIDEOS_KEY);
    if (!data) {
      await redis.set(VIDEOS_KEY, JSON.stringify(SEED_VIDEOS));
      return SEED_VIDEOS;
    }
    return parseOrArray(data, SEED_VIDEOS);
  }
  if (!memoryVideos) memoryVideos = [...SEED_VIDEOS];
  return memoryVideos;
}

export async function getVideoById(id) {
  const videos = await getVideos();
  return videos.find((v) => v.id === id) || null;
}

export async function saveVideos(videos) {
  if (hasRedis) {
    await redis.set(VIDEOS_KEY, JSON.stringify(videos));
  } else {
    memoryVideos = videos;
  }
  return videos;
}

export async function addVideo(video) {
  const videos = await getVideos();
  const newVideo = {
    id:
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `v-${Date.now()}`,
    createdAt: new Date().toISOString(),
    ...video,
  };
  const updated = [newVideo, ...videos];
  await saveVideos(updated);
  return newVideo;
}

export async function updateVideo(id, patch) {
  const videos = await getVideos();
  let updatedVideo = null;
  const updated = videos.map((v) => {
    if (v.id === id) {
      updatedVideo = { ...v, ...patch, id: v.id };
      return updatedVideo;
    }
    return v;
  });
  await saveVideos(updated);
  return updatedVideo;
}

export async function deleteVideo(id) {
  const videos = await getVideos();
  const updated = videos.filter((v) => v.id !== id);
  await saveVideos(updated);
  return updated;
}

export async function getOrders() {
  if (hasRedis) {
    const data = await redis.get(ORDERS_KEY);
    return parseOrArray(data, []);
  }
  return memoryOrders;
}

export async function saveOrders(orders) {
  if (hasRedis) {
    await redis.set(ORDERS_KEY, JSON.stringify(orders));
  } else {
    memoryOrders = orders;
  }
  return orders;
}

export async function addOrder(order) {
  const orders = await getOrders();
  const newOrder = {
    id:
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `o-${Date.now()}`,
    status: "pending",
    createdAt: new Date().toISOString(),
    ...order,
  };
  const updated = [newOrder, ...orders];
  await saveOrders(updated);
  return newOrder;
}

export async function updateOrderStatus(id, status) {
  const orders = await getOrders();
  let updatedOrder = null;
  const updated = orders.map((o) => {
    if (o.id === id) {
      updatedOrder = { ...o, status };
      return updatedOrder;
    }
    return o;
  });
  await saveOrders(updated);
  return updatedOrder;
}

export function formatPrice(price) {
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: Number.isInteger(price) ? 0 : 2,
  }).format(price);
}

// Ändere diesen Wert, um einen anderen PayPal.me-Link zu verwenden.
export const PAYPAL_HANDLE = "vikavalora";

export function buildPaypalLink(price) {
  const amount = Number(price).toFixed(2).replace(/\.00$/, "");
  return `https://paypal.me/${PAYPAL_HANDLE}/${amount}EUR`;
}
