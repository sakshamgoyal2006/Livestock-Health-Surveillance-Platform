"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { getIdentity } from "@/lib/api";

export default function HomePage() {
  const router = useRouter();
  useEffect(() => {
    router.replace(getIdentity() ? "/dashboard" : "/login");
  }, [router]);
  return <main className="center-card">Opening Pashu Seva…</main>;
}
