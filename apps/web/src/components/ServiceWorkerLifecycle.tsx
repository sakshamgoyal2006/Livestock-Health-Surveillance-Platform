"use client";

import { useEffect } from "react";

import { syncPending } from "@/lib/offline";

export function ServiceWorkerLifecycle() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    }
    const synchronize = () => void syncPending();
    window.addEventListener("online", synchronize);
    if (navigator.onLine) synchronize();
    return () => window.removeEventListener("online", synchronize);
  }, []);
  return null;
}
