import { NextResponse } from "next/server";
import { addOrder, getOrders, getVideoById } from "@/lib/data";
import { isAdminRequest } from "@/lib/auth";

export async function POST(request) {
  let body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid-json" }, { status: 400 });
  }

  const { videoId, contact } = body || {};

  if (!videoId || typeof contact !== "string" || !contact.trim()) {
    return NextResponse.json(
      { error: "videoId und contact sind erforderlich" },
      { status: 400 }
    );
  }

  const video = await getVideoById(videoId);
  if (!video) {
    return NextResponse.json({ error: "video-not-found" }, { status: 404 });
  }

  const order = await addOrder({
    videoId: video.id,
    videoTitle: video.title,
    price: video.price,
    contact: contact.trim(),
  });

  return NextResponse.json({ order }, { status: 201 });
}

export async function GET(request) {
  if (!isAdminRequest(request)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const orders = await getOrders();
  return NextResponse.json({ orders });
}
