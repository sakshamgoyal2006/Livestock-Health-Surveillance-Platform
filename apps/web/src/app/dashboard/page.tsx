"use client";

import type { Role } from "@sih/contracts";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { getIdentity } from "@/lib/api";

const dashboardCards: Record<
  Role,
  { href: string; title: string; text: string }[]
> = {
  FARMER: [
    {
      href: "/registry",
      title: "Animal registry",
      text: "Add a farm, herd, or animal.",
    },
    {
      href: "/report/new",
      title: "Report health concern",
      text: "Works without connectivity after this page is loaded.",
    },
    {
      href: "/sync",
      title: "Sync center",
      text: "See reports waiting safely on this device.",
    },
  ],
  FIELD_WORKER: [
    {
      href: "/registry",
      title: "Field registry",
      text: "Register the farm and animal being visited.",
    },
    {
      href: "/report/new",
      title: "Record field report",
      text: "Queue guided observations offline.",
    },
    {
      href: "/sync",
      title: "Sync center",
      text: "Review retry and conflict states.",
    },
  ],
  VETERINARIAN: [
    {
      href: "/vet/queue",
      title: "Veterinary queue",
      text: "Review synchronized observations; verification is required.",
    },
  ],
  DISTRICT_OFFICER: [
    {
      href: "/officer",
      title: "Operational overview",
      text: "Checkpoint 1 role shell and scope boundary.",
    },
  ],
  ADMIN: [
    {
      href: "/admin",
      title: "Audit viewer",
      text: "Inspect development audit events.",
    },
    {
      href: "/vet/queue",
      title: "Queue audit",
      text: "Inspect synchronized case records.",
    },
  ],
};

export default function DashboardPage() {
  const [role, setRole] = useState<Role>("FARMER");
  useEffect(() => setRole(getIdentity()?.role ?? "FARMER"), []);
  return (
    <AppShell>
      <p className="eyebrow">Checkpoint 1</p>
      <h1>Welcome</h1>
      <p className="notice">
        No result in this checkpoint is a diagnosis. Reports are observations
        awaiting veterinary review.
      </p>
      <section className="grid" aria-label="Role actions">
        {dashboardCards[role].map((card) => (
          <Link className="card card-link" href={card.href} key={card.href}>
            <h2>{card.title}</h2>
            <p>{card.text}</p>
          </Link>
        ))}
      </section>
    </AppShell>
  );
}
