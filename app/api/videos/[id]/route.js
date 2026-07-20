import { NextResponse } from "next/server";
import { deleteVideo, updateVideo } from "@/lib/data";
import { isAdminRequest } from "@/lib/auth";

export async function PUT(request, { params }) {
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

  const { title, description, price, thumbnail } = body || {};
  const patch = {};
  if (title !== undefined) patch.title = String(title).trim();
  if (description !== undefined) patch.description = String(description).trim();
  if (thumbnail !== undefined) patch.thumbnail = String(thumbnail).trim();
  if (price !== undefined) {
    const numericPrice = Number(price);
    if (Number.isNaN(numericPrice) || numericPrice < 0) {
      return NextResponse.json({ error: "invalid-price" }, { status: 400 });
    }
    patch.price = numericPrice;
  }

  const updated = await updateVideo(id, patch);
  if (!updated) {
    return NextResponse.json({ error: "video-not-found" }, { status: 404 });
  }

  return NextResponse.json({ video: updated });
}

export async function DELETE(request, { params }) {
  if (!isAdminRequest(request)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const { id } = await params;
  const updated = await deleteVideo(id);
  return NextResponse.json({ videos: updated });
}
