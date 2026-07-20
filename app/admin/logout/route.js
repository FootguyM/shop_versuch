import { NextResponse } from "next/server";
import { ADMIN_COOKIE_NAME } from "@/lib/auth";

export async function GET(request) {
  const origin = new URL(request.url).origin;
  const response = NextResponse.redirect(new URL("/", origin));
  response.cookies.set(ADMIN_COOKIE_NAME, "", { maxAge: 0, path: "/" });
  return response;
}
