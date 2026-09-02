"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { apiFetch } from "@/lib/api";

type Advisory = {
  id: string;
  report_id: string;
  language: string;
  content: string;
  review_status: string;
};

export default function AdvisoriesPage() {
  const [items, setItems] = useState<Advisory[]>([]);
  useEffect(
    () => void apiFetch<Advisory[]>("/api/v1/advisories").then(setItems),
    [],
  );
  return (
    <AppShell allowedRoles={["FARMER", "FIELD_WORKER"]}>
      <p className="eyebrow">Multilingual guidance</p>
      <h1>Advisories</h1>
      <p className="notice">
        Template guidance only. It does not confirm a diagnosis and does not
        replace veterinary care.
      </p>
      <ul className="list">
        {items.map((item) => (
          <li key={item.id}>
            <strong>{item.language.toUpperCase()}</strong>
            <p>{item.content}</p>
            <small>
              {item.review_status} · report {item.report_id}
            </small>
          </li>
        ))}
        {!items.length && <li>No synchronized advisory yet.</li>}
      </ul>
    </AppShell>
  );
}
