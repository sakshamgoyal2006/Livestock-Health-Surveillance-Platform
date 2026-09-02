"use client";

import { AppShell } from "@/components/AppShell";

export default function OfficerPage() {
  return (
    <AppShell allowedRoles={["DISTRICT_OFFICER"]}>
      <p className="eyebrow">District officer shell</p>
      <h1>Operational overview</h1>
      <div className="notice">
        Checkpoint 1 establishes authorized navigation only. Aggregated trends,
        GIS, alerts, and hotspot candidates are intentionally deferred; this
        screen never labels synchronized reports as an outbreak.
      </div>
      <section className="grid">
        <div className="card">
          <h2>Queue operations</h2>
          <p>
            Veterinary workload summaries will appear only after
            privacy-preserving aggregation is implemented.
          </p>
        </div>
        <div className="card">
          <h2>Surveillance map</h2>
          <p>No map is rendered from individual reports at this checkpoint.</p>
        </div>
        <div className="card">
          <h2>Escalations</h2>
          <p>No public-health action is dispatched automatically.</p>
        </div>
      </section>
    </AppShell>
  );
}
