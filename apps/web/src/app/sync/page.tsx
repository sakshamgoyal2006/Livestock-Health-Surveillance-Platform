"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { listMutations, type QueuedMutation, syncPending } from "@/lib/offline";

export default function SyncPage() {
  const [items, setItems] = useState<QueuedMutation[]>([]);
  const [busy, setBusy] = useState(false);
  const [online, setOnline] = useState(true);

  const refresh = useCallback(async () => setItems(await listMutations()), []);
  useEffect(() => {
    setOnline(navigator.onLine);
    void refresh();
    const connectionChanged = () => {
      setOnline(navigator.onLine);
      if (navigator.onLine) void syncPending(true).then(refresh);
    };
    window.addEventListener("online", connectionChanged);
    window.addEventListener("offline", connectionChanged);
    return () => {
      window.removeEventListener("online", connectionChanged);
      window.removeEventListener("offline", connectionChanged);
    };
  }, [refresh]);

  const counts = useMemo(
    () =>
      items.reduce<Record<string, number>>((result, item) => {
        result[item.state] = (result[item.state] ?? 0) + 1;
        return result;
      }, {}),
    [items],
  );

  async function synchronize() {
    setBusy(true);
    await syncPending(true);
    await refresh();
    setBusy(false);
  }

  return (
    <AppShell allowedRoles={["FARMER", "FIELD_WORKER"]}>
      <p className="eyebrow">Offline storage</p>
      <h1>Sync center</h1>
      <p className={online ? "success" : "notice"}>
        {online
          ? "Connectivity available."
          : "Offline. Pending reports remain durable on this device."}
      </p>
      <div className="grid">
        {(["PENDING", "SYNCING", "ACKED", "FAILED", "CONFLICT"] as const).map(
          (state) => (
            <div className="card" key={state}>
              <strong>{state}</strong>
              <div>{counts[state] ?? 0}</div>
            </div>
          ),
        )}
      </div>
      <p>
        <button
          data-testid="sync-now"
          disabled={!online || busy}
          onClick={() => void synchronize()}
        >
          {busy ? "Synchronizing…" : "Synchronize now"}
        </button>
      </p>
      <ul className="list" data-testid="sync-items">
        {items.map((item) => (
          <li key={item.client_mutation_id} data-sync-state={item.state}>
            <strong>{item.state}</strong> · report{" "}
            <code>{String(item.payload.id)}</code>
            <div className="muted">
              Mutation <code>{item.client_mutation_id}</code> · attempts{" "}
              {item.attempts}
            </div>
            {item.last_error && (
              <div className="danger-text">{item.last_error}</div>
            )}
          </li>
        ))}
        {!items.length && <li>No local mutations yet.</li>}
      </ul>
    </AppShell>
  );
}
