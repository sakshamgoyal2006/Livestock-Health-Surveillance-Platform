"use client";

import type { Role } from "@sih/contracts";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { devLogin } from "@/lib/api";

const identities: Record<Role, string> = {
  FARMER: "farmer@example.com",
  FIELD_WORKER: "field@example.com",
  VETERINARIAN: "vet@example.com",
  DISTRICT_OFFICER: "officer@example.com",
  ADMIN: "admin@example.com",
};

export default function LoginPage() {
  const router = useRouter();
  const [role, setRole] = useState<Role>("FARMER");
  const [email, setEmail] = useState(identities.FARMER);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const user = await devLogin(email, role);
      if (user.role === "VETERINARIAN") router.push("/vet/queue");
      else if (user.role === "DISTRICT_OFFICER") router.push("/officer");
      else if (user.role === "ADMIN") router.push("/admin");
      else router.push("/dashboard");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="center-card">
      <p className="eyebrow">Synthetic development environment</p>
      <h1>Pashu Seva</h1>
      <p>
        Sign in with a seeded demo identity. No real account or clinical
        identity is implied.
      </p>
      <form onSubmit={submit}>
        <label className="field">
          Role
          <select
            aria-label="Role"
            data-testid="role-select"
            value={role}
            onChange={(event) => {
              const nextRole = event.target.value as Role;
              setRole(nextRole);
              setEmail(identities[nextRole]);
            }}
          >
            {Object.keys(identities).map((item) => (
              <option key={item} value={item}>
                {item.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Synthetic email
          <input
            data-testid="email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label className="field">
          Development password
          <input type="password" value="dev-only" readOnly />
        </label>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        <button data-testid="login-submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="notice">
        This prototype records observations for veterinary review. It does not
        diagnose disease.
      </p>
    </main>
  );
}
