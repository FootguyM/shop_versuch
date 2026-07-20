"use client";

import { useState } from "react";
import Link from "next/link";
import { formatPrice } from "@/lib/data";

const EMPTY_FORM = { title: "", description: "", price: "", thumbnail: "" };

export default function AdminDashboard({
  initialVideos,
  initialOrders,
  noDatabase,
}) {
  const [videos, setVideos] = useState(initialVideos);
  const [orders, setOrders] = useState(initialOrders);
  const [tab, setTab] = useState("videos");

  const [newVideo, setNewVideo] = useState(EMPTY_FORM);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState(null);

  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState(EMPTY_FORM);
  const [savingEdit, setSavingEdit] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [updatingOrderId, setUpdatingOrderId] = useState(null);

  async function handleAddVideo(e) {
    e.preventDefault();
    setAddError(null);

    if (!newVideo.title.trim() || !newVideo.thumbnail.trim() || newVideo.price === "") {
      setAddError("Titel, Preis und Thumbnail-URL sind erforderlich.");
      return;
    }

    setAdding(true);
    try {
      const res = await fetch("/api/videos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newVideo),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "request-failed");
      setVideos((prev) => [data.video, ...prev]);
      setNewVideo(EMPTY_FORM);
    } catch (err) {
      setAddError("Video konnte nicht hinzugefügt werden. Bitte prüfe die Angaben.");
    } finally {
      setAdding(false);
    }
  }

  function startEdit(video) {
    setEditingId(video.id);
    setEditForm({
      title: video.title,
      description: video.description,
      price: video.price,
      thumbnail: video.thumbnail,
    });
  }

  function cancelEdit() {
    setEditingId(null);
    setEditForm(EMPTY_FORM);
  }

  async function handleSaveEdit(id) {
    setSavingEdit(true);
    try {
      const res = await fetch(`/api/videos/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editForm),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "request-failed");
      setVideos((prev) => prev.map((v) => (v.id === id ? data.video : v)));
      cancelEdit();
    } catch {
      alert("Speichern fehlgeschlagen. Bitte versuch es erneut.");
    } finally {
      setSavingEdit(false);
    }
  }

  async function handleDelete(id) {
    if (!confirm("Dieses Video wirklich löschen?")) return;
    setDeletingId(id);
    try {
      const res = await fetch(`/api/videos/${id}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error("request-failed");
      setVideos(data.videos);
    } catch {
      alert("Löschen fehlgeschlagen. Bitte versuch es erneut.");
    } finally {
      setDeletingId(null);
    }
  }

  async function toggleOrderStatus(order) {
    const nextStatus = order.status === "fulfilled" ? "pending" : "fulfilled";
    setUpdatingOrderId(order.id);
    try {
      const res = await fetch(`/api/orders/${order.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error("request-failed");
      setOrders((prev) =>
        prev.map((o) => (o.id === order.id ? data.order : o))
      );
    } catch {
      alert("Status konnte nicht aktualisiert werden.");
    } finally {
      setUpdatingOrderId(null);
    }
  }

  const pendingCount = orders.filter((o) => o.status !== "fulfilled").length;

  return (
    <div className="min-h-screen bg-ink font-body text-porcelain">
      <header className="sticky top-0 z-40 border-b border-hairline bg-ink/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
          <span className="font-display text-lg">
            Admin <span className="text-brass">·</span> Reelroom
          </span>
          <nav className="flex items-center gap-5 font-mono text-xs uppercase tracking-widest text-stone">
            <Link href="/" className="transition-colors hover:text-brass">
              Zur Website
            </Link>
            <a
              href="/admin/logout"
              className="transition-colors hover:text-brass"
            >
              Abmelden
            </a>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 py-10 sm:px-8">
        {noDatabase && (
          <div className="mb-8 rounded-lg border border-brass/40 bg-brass/10 p-4 text-sm text-brass-soft">
            <strong className="font-semibold">Keine Datenbank verbunden.</strong>{" "}
            Änderungen funktionieren zum Testen, werden aber nicht dauerhaft
            gespeichert. Verbinde eine Upstash-Redis-Datenbank über Vercel
            (siehe README.md), damit Änderungen dauerhaft erhalten bleiben.
          </div>
        )}

        <div className="mb-8 flex gap-2 border-b border-hairline">
          {[
            { key: "videos", label: `Videos (${videos.length})` },
            { key: "orders", label: `Bestellungen (${pendingCount} offen)` },
          ].map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`border-b-2 px-4 py-3 font-mono text-xs uppercase tracking-widest transition-colors ${
                tab === t.key
                  ? "border-brass text-brass"
                  : "border-transparent text-stone hover:text-porcelain"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === "videos" && (
          <div className="space-y-10">
            <section className="rounded-lg border border-hairline bg-panel p-6">
              <h2 className="font-display text-lg text-porcelain">
                Neues Video hinzufügen
              </h2>
              <form
                onSubmit={handleAddVideo}
                className="mt-4 grid gap-4 sm:grid-cols-2"
              >
                <Field label="Titel">
                  <input
                    className="admin-input"
                    value={newVideo.title}
                    onChange={(e) =>
                      setNewVideo({ ...newVideo, title: e.target.value })
                    }
                  />
                </Field>
                <Field label="Preis (EUR)">
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    className="admin-input"
                    value={newVideo.price}
                    onChange={(e) =>
                      setNewVideo({ ...newVideo, price: e.target.value })
                    }
                  />
                </Field>
                <Field label="Thumbnail-URL" full>
                  <input
                    className="admin-input"
                    value={newVideo.thumbnail}
                    onChange={(e) =>
                      setNewVideo({ ...newVideo, thumbnail: e.target.value })
                    }
                    placeholder="https://..."
                  />
                </Field>
                <Field label="Beschreibung" full>
                  <textarea
                    className="admin-input min-h-24"
                    value={newVideo.description}
                    onChange={(e) =>
                      setNewVideo({
                        ...newVideo,
                        description: e.target.value,
                      })
                    }
                  />
                </Field>
                {addError && (
                  <p className="text-sm text-red-400 sm:col-span-2">
                    {addError}
                  </p>
                )}
                <div className="sm:col-span-2">
                  <button
                    type="submit"
                    disabled={adding}
                    className="rounded-md bg-brass px-6 py-3 font-mono text-xs uppercase tracking-widest text-ink transition-colors hover:bg-brass-soft disabled:opacity-60"
                  >
                    {adding ? "Wird hinzugefügt…" : "Video hinzufügen"}
                  </button>
                </div>
              </form>
            </section>

            <section>
              <h2 className="mb-4 font-display text-lg text-porcelain">
                Vorhandene Videos
              </h2>
              <div className="space-y-4">
                {videos.map((video) => (
                  <div
                    key={video.id}
                    className="rounded-lg border border-hairline bg-panel p-5"
                  >
                    {editingId === video.id ? (
                      <div className="grid gap-4 sm:grid-cols-2">
                        <Field label="Titel">
                          <input
                            className="admin-input"
                            value={editForm.title}
                            onChange={(e) =>
                              setEditForm({
                                ...editForm,
                                title: e.target.value,
                              })
                            }
                          />
                        </Field>
                        <Field label="Preis (EUR)">
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            className="admin-input"
                            value={editForm.price}
                            onChange={(e) =>
                              setEditForm({
                                ...editForm,
                                price: e.target.value,
                              })
                            }
                          />
                        </Field>
                        <Field label="Thumbnail-URL" full>
                          <input
                            className="admin-input"
                            value={editForm.thumbnail}
                            onChange={(e) =>
                              setEditForm({
                                ...editForm,
                                thumbnail: e.target.value,
                              })
                            }
                          />
                        </Field>
                        <Field label="Beschreibung" full>
                          <textarea
                            className="admin-input min-h-24"
                            value={editForm.description}
                            onChange={(e) =>
                              setEditForm({
                                ...editForm,
                                description: e.target.value,
                              })
                            }
                          />
                        </Field>
                        <div className="flex gap-3 sm:col-span-2">
                          <button
                            onClick={() => handleSaveEdit(video.id)}
                            disabled={savingEdit}
                            className="rounded-md bg-brass px-5 py-2.5 font-mono text-xs uppercase tracking-widest text-ink hover:bg-brass-soft disabled:opacity-60"
                          >
                            {savingEdit ? "Speichert…" : "Speichern"}
                          </button>
                          <button
                            onClick={cancelEdit}
                            className="rounded-md border border-hairline px-5 py-2.5 font-mono text-xs uppercase tracking-widest text-stone hover:text-porcelain"
                          >
                            Abbrechen
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={video.thumbnail}
                          alt={video.title}
                          className="h-20 w-32 flex-shrink-0 rounded-md object-cover"
                        />
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-display text-base text-porcelain">
                            {video.title}
                          </p>
                          <p className="mt-1 line-clamp-1 text-sm text-stone">
                            {video.description}
                          </p>
                          <p className="mt-1 font-mono text-sm text-brass">
                            {formatPrice(video.price)}
                          </p>
                        </div>
                        <div className="flex flex-shrink-0 gap-2">
                          <button
                            onClick={() => startEdit(video)}
                            className="rounded-md border border-hairline px-4 py-2 font-mono text-xs uppercase tracking-widest text-stone hover:border-brass/60 hover:text-brass"
                          >
                            Bearbeiten
                          </button>
                          <button
                            onClick={() => handleDelete(video.id)}
                            disabled={deletingId === video.id}
                            className="rounded-md border border-hairline px-4 py-2 font-mono text-xs uppercase tracking-widest text-stone hover:border-red-400/60 hover:text-red-400 disabled:opacity-60"
                          >
                            {deletingId === video.id ? "…" : "Löschen"}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
                {videos.length === 0 && (
                  <p className="text-sm text-stone">
                    Noch keine Videos vorhanden.
                  </p>
                )}
              </div>
            </section>
          </div>
        )}

        {tab === "orders" && (
          <section className="overflow-x-auto rounded-lg border border-hairline">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="border-b border-hairline bg-panel font-mono text-[11px] uppercase tracking-widest text-stone">
                <tr>
                  <th className="px-4 py-3">Datum</th>
                  <th className="px-4 py-3">Video</th>
                  <th className="px-4 py-3">Preis</th>
                  <th className="px-4 py-3">Kontakt</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr
                    key={order.id}
                    className="border-b border-hairline last:border-0"
                  >
                    <td className="px-4 py-3 text-stone">
                      {new Date(order.createdAt).toLocaleString("de-DE")}
                    </td>
                    <td className="px-4 py-3">{order.videoTitle}</td>
                    <td className="px-4 py-3 font-mono text-brass">
                      {formatPrice(order.price)}
                    </td>
                    <td className="px-4 py-3">{order.contact}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-full px-2.5 py-1 font-mono text-[11px] uppercase tracking-widest ${
                          order.status === "fulfilled"
                            ? "bg-brass/15 text-brass"
                            : "bg-stone/15 text-stone"
                        }`}
                      >
                        {order.status === "fulfilled" ? "Erledigt" : "Offen"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => toggleOrderStatus(order)}
                        disabled={updatingOrderId === order.id}
                        className="rounded-md border border-hairline px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-stone hover:border-brass/60 hover:text-brass disabled:opacity-60"
                      >
                        {order.status === "fulfilled"
                          ? "Als offen markieren"
                          : "Als erledigt markieren"}
                      </button>
                    </td>
                  </tr>
                ))}
                {orders.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-4 py-8 text-center text-stone"
                    >
                      Noch keine Bestellungen eingegangen.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </section>
        )}
      </main>
    </div>
  );
}

function Field({ label, children, full }) {
  return (
    <label className={`block ${full ? "sm:col-span-2" : ""}`}>
      <span className="mb-1.5 block font-mono text-[11px] uppercase tracking-widest text-stone">
        {label}
      </span>
      {children}
    </label>
  );
}
