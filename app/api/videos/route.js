import { NextResponse } from "next/server";
import { addVideo, getVideos } from "@/lib/data";
import { isAdminRequest } from "@/lib/auth";

export async function GET() {
  const videos = await getVideos();
  return NextResponse.json({ videos });
}

export async function POST(request) {
  if (!isAdminRequest(request)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid-json" }, { status: 400 });
  }

  const { title, description, price, thumbnail } = body || {};

  if (!title || !thumbnail || price === undefined || price === null) {
    return NextResponse.json(
      { error: "title, price und thumbnail sind erforderlich" },
      { status: 400 }
    );
  }

  const numericPrice = Number(price);
  if (Number.isNaN(numericPrice) || numericPrice < 0) {
    return NextResponse.json({ error: "invalid-price" }, { status: 400 });
  }

  const video = await addVideo({
    title: String(title).trim(),
    description: String(description || "").trim(),
    price: numericPrice,
    thumbnail: String(thumbnail).trim(),
  });

  return NextResponse.json({ video }, { status: 201 });
}
