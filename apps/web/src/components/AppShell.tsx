"use client";

import type { Role, UserIdentity } from "@sih/contracts";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";

import { clearSession, getIdentity } from "@/lib/api";

const roleLinks: Record<Role, { href: string; label: string }[]> = {
  FARMER: [
    { href: "/dashboard", label: "Home" },
    { href: "/registry", label: "Animals & herds" },
    { href: "/report/new", label: "New report" },
    { href: "/sync", label: "Sync center" },
    { href: "/advisories", label: "Advisories" },
  ],
  FIELD_WORKER: [
    { href: "/dashboard", label: "Home" },
    { href: "/registry", label: "Field registry" },
    { href: "/report/new", label: "New report" },
    { href: "/sync", label: "Sync center" },
    { href: "/advisories", label: "Advisories" },
  ],
  VETERINARIAN: [
    { href: "/dashboard", label: "Home" },
    { href: "/vet/queue", label: "Case queue" },
  ],
  DISTRICT_OFFICER: [
    { href: "/dashboard", label: "Home" },
    { href: "/officer", label: "Operations" },
  ],
  ADMIN: [
    { href: "/dashboard", label: "Home" },
    { href: "/admin", label: "Administration" },
    { href: "/admin/mlops", label: "Model governance" },
    { href: "/vet/queue", label: "Case audit" },
  ],
};

export function AppShell({
  children,
  allowedRoles,
}: {
  children: ReactNode;
  allowedRoles?: Role[];
}) {
  const router = useRouter();
  const rolesKey = allowedRoles?.join(",") ?? "";
  const [identity, setIdentity] = useState<UserIdentity | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = getIdentity();
    if (!stored) {
      router.replace("/login");
      return;
    }
    const roles = rolesKey ? (rolesKey.split(",") as Role[]) : null;
    if (roles && !roles.includes(stored.role)) {
      router.replace("/dashboard");
      return;
    }
    setIdentity(stored);
    setReady(true);
  }, [rolesKey, router]);

  if (!ready || !identity)
    return <main className="center-card">Checking access…</main>;

  return (
    <div className="app-frame">
      <header className="topbar">
        <Link href="/dashboard" className="brand">
          Pashu Seva
        </Link>
        <div className="identity">
          <span>{identity.display_name}</span>
          <span className="role-badge">
            {identity.role.replaceAll("_", " ")}
          </span>
          <button
            className="link-button"
            onClick={() => {
              clearSession();
              router.replace("/login");
            }}
          >
            Sign out
          </button>
        </div>
      </header>
      <nav className="nav" aria-label="Primary navigation">
        {roleLinks[identity.role].map((item) => (
          <Link key={item.href} href={item.href}>
            {item.label}
          </Link>
        ))}
      </nav>
      <main className="content">{children}</main>
      <footer>
        Triage support prototype · Not a diagnosis · Veterinary verification
        required
      </footer>
    </div>
  );
}
