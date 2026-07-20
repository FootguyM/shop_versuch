import { NextResponse } from "next/server";
import { updateOrderStatus } from "@/lib/data";
import { isAdminRequest } from "@/lib/auth";

export async function PATCH(request, { params }) {
  if (!isAdminRequest(request)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const { id } = await params;
  let body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid-json" }, { status: 400 });
  }

  const { status } = body || {};
  if (!["pending", "fulfilled"].includes(status)) {
    return NextResponse.json({ error: "invalid-status" }, { status: 400 });
  }

  const updated = await updateOrderStatus(id, status);
  if (!updated) {
    return NextResponse.json({ error: "order-not-found" }, { status: 404 });
  }

  return NextResponse.json({ order: updated });
}
