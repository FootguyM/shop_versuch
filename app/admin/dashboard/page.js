import { redirect } from "next/navigation";
import { isAdminAuthenticated } from "@/lib/auth";
import { getVideos, getOrders } from "@/lib/data";
import { hasRedis } from "@/lib/redis";
import AdminDashboard from "@/components/AdminDashboard";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Admin — Reelroom",
  robots: { index: false, follow: false },
};

export default async function AdminDashboardPage() {
  const authed = await isAdminAuthenticated();
  if (!authed) redirect("/");

  const [videos, orders] = await Promise.all([getVideos(), getOrders()]);

  return (
    <AdminDashboard
      initialVideos={videos}
      initialOrders={orders}
      noDatabase={!hasRedis}
    />
  );
}
