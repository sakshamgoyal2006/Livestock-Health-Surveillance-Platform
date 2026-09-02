"use client";

import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { apiFetch } from "@/lib/api";

type Aggregate = {
  area_name: string;
  suspected_count: number;
  vet_verified_count: number;
  lab_confirmed_count: number;
  latitude: number | null;
  longitude: number | null;
  coordinates_suppressed: boolean;
};
type Hotspot = {
  id: string;
  area_name: string;
  status: string;
  observed_count: number;
  suspected_count: number;
  vet_verified_count: number;
  lab_confirmed_count: number;
  baseline_daily_rate: number;
  confidence: number;
  detector_version: string;
  notice: string;
};
type Alert = {
  id: string;
  type: string;
  status: string;
  context: Record<string, unknown>;
};

export default function OfficerPage() {
  const [aggregates, setAggregates] = useState<Aggregate[]>([]);
  const [hotspots, setHotspots] = useState<Hotspot[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      const [map, hotspotRows, alertRows] = await Promise.all([
        apiFetch<{ items: Aggregate[] }>(
          "/api/v1/surveillance/aggregates?level=VILLAGE",
        ),
        apiFetch<Hotspot[]>("/api/v1/surveillance/hotspots"),
        apiFetch<Alert[]>("/api/v1/alerts"),
      ]);
      setAggregates(map.items);
      setHotspots(hotspotRows);
      setAlerts(alertRows);
      setError("");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not load surveillance data",
      );
    }
  }, []);
  useEffect(() => void load(), [load]);
  async function acknowledge(id: string) {
    await apiFetch(`/api/v1/surveillance/hotspots/${id}/acknowledge`, {
      method: "POST",
      body: JSON.stringify({ note: "Reviewed in district dashboard" }),
    });
    await load();
  }
  return (
    <AppShell allowedRoles={["DISTRICT_OFFICER", "ADMIN"]}>
      <p className="eyebrow">Privacy-preserving surveillance</p>
      <h1>District operations</h1>
      <p className="notice">
        Signals below are hotspot candidates—not confirmed outbreaks.
        Coordinates are rounded and suppressed for groups smaller than two.
      </p>
      {error && <p className="error">{error}</p>}
      <section className="card" data-testid="surveillance-map">
        <h2>Independent status layers</h2>
        <div className="map-legend">
          <span className="suspected-dot" /> Suspected{" "}
          <span className="verified-dot" /> Vet verified{" "}
          <span className="lab-dot" /> Lab confirmed
        </div>
        <div className="aggregate-map">
          {aggregates.map((area) => (
            <div
              className="map-point"
              key={area.area_name}
              data-testid={`map-area-${area.area_name}`}
            >
              <strong>{area.area_name}</strong>
              <div data-testid="suspected-layer">
                Suspected {area.suspected_count}
              </div>
              <div data-testid="verified-layer">
                Vet verified {area.vet_verified_count}
              </div>
              <div data-testid="lab-layer">Lab {area.lab_confirmed_count}</div>
              <small>
                {area.coordinates_suppressed
                  ? "Location suppressed"
                  : `${area.latitude}, ${area.longitude}`}
              </small>
            </div>
          ))}
        </div>
      </section>
      <section>
        <h2>Hotspot candidates</h2>
        <div className="grid">
          {hotspots.map((item) => (
            <article
              className="card"
              key={item.id}
              data-testid="hotspot-candidate"
            >
              <h3>{item.area_name}</h3>
              <strong>{item.status.replaceAll("_", " ")}</strong>
              <p>
                Observed {item.observed_count} · baseline{" "}
                {item.baseline_daily_rate.toFixed(2)}/day
              </p>
              <p>
                Suspected {item.suspected_count} · verified{" "}
                {item.vet_verified_count} · lab {item.lab_confirmed_count}
              </p>
              <p>
                Confidence {Math.round(item.confidence * 100)}% ·{" "}
                {item.detector_version}
              </p>
              <small>{item.notice}</small>
              {item.status === "CANDIDATE" && (
                <button
                  data-testid="acknowledge-hotspot"
                  onClick={() => void acknowledge(item.id)}
                >
                  Acknowledge candidate
                </button>
              )}
            </article>
          ))}
        </div>
      </section>
      <section>
        <h2>Development alert ledger</h2>
        <ul className="list">
          {alerts.map((alert) => (
            <li key={alert.id}>
              <strong>{alert.type}</strong> · {alert.status}
              <pre>{JSON.stringify(alert.context, null, 2)}</pre>
            </li>
          ))}
        </ul>
      </section>
    </AppShell>
  );
}
