"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { apiFetch } from "@/lib/api";

type Overview = {
  candidates: Array<Record<string, unknown>>;
  datasets: Array<Record<string, unknown>>;
  models: Array<Record<string, unknown>>;
  controls: Record<string, boolean>;
};

export default function ModelGovernancePage() {
  const [data, setData] = useState<Overview | null>(null);
  useEffect(
    () => void apiFetch<Overview>("/api/v1/mlops/overview").then(setData),
    [],
  );
  return (
    <AppShell allowedRoles={["ADMIN"]}>
      <p className="eyebrow">Verified active learning</p>
      <h1>Model governance</h1>
      <p className="notice">
        No prediction is a training label. Candidates require authorized
        verification, quality review, immutable batching, regression checks, and
        a separate manual approval. Nothing auto-deploys.
      </p>
      <div className="grid">
        <section className="card">
          <h2>Safety controls</h2>
          <pre>{JSON.stringify(data?.controls ?? {}, null, 2)}</pre>
        </section>
        <section className="card">
          <h2>Staging candidates</h2>
          <pre>{JSON.stringify(data?.candidates ?? [], null, 2)}</pre>
        </section>
        <section className="card">
          <h2>Immutable datasets</h2>
          <pre>{JSON.stringify(data?.datasets ?? [], null, 2)}</pre>
        </section>
        <section className="card">
          <h2>Models and comparisons</h2>
          <pre>{JSON.stringify(data?.models ?? [], null, 2)}</pre>
        </section>
      </div>
    </AppShell>
  );
}
