import { NextResponse } from "next/server";
import { ADMIN_COOKIE_NAME, adminCookieOptions } from "@/lib/auth";

export async function GET(request, { params }) {
  const { token } = await params;
  const adminToken = process.env.ADMIN_TOKEN;
  const origin = new URL(request.url).origin;

  // Kein ADMIN_TOKEN gesetzt oder falscher Link: unauffällig zur Startseite.
  // (Bewusst kein Hinweis, ob der Link "fast richtig" war.)
  if (!adminToken || token !== adminToken) {
    return NextResponse.redirect(new URL("/", origin));
  }

  const response = NextResponse.redirect(new URL("/admin/dashboard", origin));
  response.cookies.set(ADMIN_COOKIE_NAME, adminToken, adminCookieOptions);
  return response;
}
