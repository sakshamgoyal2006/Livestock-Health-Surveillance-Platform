import type { Role, UserIdentity } from "@sih/contracts";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const TOKEN_KEY = "sih.dev.token";
const USER_KEY = "sih.dev.user";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
  ) {
    super(message);
  }
}

export function storeSession(token: string, user: UserIdentity): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getToken(): string | null {
  return typeof window === "undefined" ? null : localStorage.getItem(TOKEN_KEY);
}

export function getIdentity(): UserIdentity | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserIdentity;
  } catch {
    clearSession();
    return null;
  }
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  const payload = (await response.json().catch(() => ({}))) as {
    error?: { code?: string; message?: string };
  };
  if (!response.ok) {
    if (response.status === 401) clearSession();
    throw new ApiError(
      payload.error?.message ?? `Request failed (${response.status})`,
      response.status,
      payload.error?.code ?? "REQUEST_FAILED",
    );
  }
  return payload as T;
}

export async function devLogin(
  email: string,
  role: Role,
): Promise<UserIdentity> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/dev-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, role, password: "dev-only" }),
  });
  const payload = (await response.json()) as {
    access_token?: string;
    user?: UserIdentity;
    error?: { message?: string };
  };
  if (!response.ok || !payload.access_token || !payload.user) {
    throw new ApiError(
      payload.error?.message ?? "Login failed",
      response.status,
      "LOGIN_FAILED",
    );
  }
  storeSession(payload.access_token, payload.user);
  return payload.user;
}
