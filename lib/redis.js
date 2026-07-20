import { Redis } from "@upstash/redis";

// Unterstützt sowohl die Namen, die Vercel beim Verbinden einer
// Upstash-Redis-Datenbank automatisch setzt (KV_REST_API_URL /
// KV_REST_API_TOKEN), als auch die "nativen" Upstash-Namen, falls die
// Datenbank direkt bei Upstash angelegt wurde.
const url = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
const token =
  process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;

export const hasRedis = Boolean(url && token);

export const redis = hasRedis ? new Redis({ url, token }) : null;
