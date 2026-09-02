"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { apiFetch } from "@/lib/api";

type AuditRow = {
  id: string;
  occurred_at: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  request_id: string;
};

export default function AdminPage() {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    apiFetch<{ items: AuditRow[] }>("/api/v1/admin/audit?page=1&page_size=50")
      .then((page) => setRows(page.items))
      .catch((reason) =>
        setError(
          reason instanceof Error ? reason.message : "Could not load audit log",
        ),
      );
  }, []);
  return (
    <AppShell allowedRoles={["ADMIN"]}>
      <p className="eyebrow">Administration</p>
      <h1>Audit viewer</h1>
      <p className="notice">
        This view intentionally excludes report free text and credentials.
      </p>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Action</th>
              <th>Resource</th>
              <th>Request ID</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{new Date(row.occurred_at).toLocaleString()}</td>
                <td>{row.action}</td>
                <td>
                  {row.resource_type} · <code>{row.resource_id}</code>
                </td>
                <td>
                  <code>{row.request_id}</code>
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={4}>No audit events yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <section className="grid">
        <div className="card">
          <h2>Reference data</h2>
          <p>
            Management behavior is deferred; no unsafe placeholder mutations are
            exposed.
          </p>
        </div>
        <div className="card">
          <h2>Model versions</h2>
          <p>No model exists in Checkpoint 1.</p>
        </div>
      </section>
    </AppShell>
  );
}
