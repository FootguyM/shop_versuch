export const ADMIN_COOKIE_NAME = "reelroom_admin";

export const adminCookieOptions = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax",
  path: "/",
  maxAge: 60 * 60 * 24 * 30, // 30 Tage
};

// Für Server Components (liest aus next/headers cookies()).
export async function isAdminAuthenticated() {
  const adminToken = process.env.ADMIN_TOKEN;
  if (!adminToken) return false;
  const { cookies } = await import("next/headers");
  const cookieStore = await cookies();
  return cookieStore.get(ADMIN_COOKIE_NAME)?.value === adminToken;
}

// Für Route Handler (liest aus dem NextRequest).
export function isAdminRequest(request) {
  const adminToken = process.env.ADMIN_TOKEN;
  if (!adminToken) return false;
  return request.cookies.get(ADMIN_COOKIE_NAME)?.value === adminToken;
}
