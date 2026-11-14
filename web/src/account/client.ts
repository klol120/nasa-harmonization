import { API_URL } from "../config";
import type { BBox } from "../data/contract";

/**
 * Client for the optional account features (backend/firecal_api/accounts.py).
 * Nothing in the data views depends on this: every chart and map works signed out.
 */

const TOKEN_KEY = "wel3a_session";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Private mode / blocked storage: the session lasts until the page is closed.
  }
}

export class AccountError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function call<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers, body });
  } catch {
    throw new AccountError("Can't reach the server. Check your connection and try again.", 0);
  }
  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    // empty or non-JSON body
  }
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    const msg =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail) && detail[0]?.msg
          ? String(detail[0].msg).replace(/^Value error, /, "")
          : `Request failed (${res.status})`;
    throw new AccountError(msg, res.status);
  }
  return data as T;
}

export interface AuthConfig {
  google_client_id: string | null;
  dev_login: boolean;
}

export interface User {
  id: number;
  email: string;
  name: string | null;
  picture: string | null;
  is_admin: boolean;
  created_at: string;
}

export type NewsletterStatus = "none" | "pending" | "confirmed" | "unsubscribed";

export interface Me {
  user: User;
  newsletter: { status: NewsletterStatus; topics: string[] };
  n_areas: number;
}

export interface AreaStatus {
  ym: string;
  harmonized: number;
  anomaly_z: number | null;
  is_estimate: boolean;
  partial_month: boolean;
  unusual: boolean;
}

export interface SavedArea {
  id: number;
  region: string;
  name: string;
  kind: "bbox" | "polygon";
  bbox: BBox;
  ring: [number, number][] | null;
  exclude_persistent: boolean;
  alert_enabled: boolean;
  alert_z: number;
  created_at: string;
  status: AreaStatus | null;
}

export interface NewArea {
  region: string;
  name: string;
  kind: "bbox" | "polygon";
  bbox: BBox;
  ring?: [number, number][] | null;
  exclude_persistent?: boolean;
  alert_enabled?: boolean;
  alert_z?: number;
}

export const api = {
  config: () => call<AuthConfig>("/auth/config"),
  me: () => call<Me>("/auth/me"),
  google: (credential: string) => call<{ token: string; user: User }>("/auth/google", { method: "POST", json: { credential } }),
  devLogin: (email: string, name?: string) => call<{ token: string; user: User }>("/auth/dev-login", { method: "POST", json: { email, name } }),
  logout: () => call<void>("/auth/logout", { method: "POST" }),
  deleteAccount: () => call<void>("/me", { method: "DELETE" }),
  subscribe: (email: string | null, source: string) =>
    call<{ status: "subscribed" | "check_email" }>("/newsletter/subscribe", { method: "POST", json: { email, source } }),
  setNewsletter: (subscribed: boolean) => call<{ status: string }>("/me/newsletter", { method: "POST", json: { subscribed } }),
  areas: () => call<SavedArea[]>("/me/areas"),
  saveArea: (a: NewArea) => call<SavedArea>("/me/areas", { method: "POST", json: a }),
  updateArea: (id: number, patch: Partial<Pick<SavedArea, "name" | "alert_enabled" | "alert_z" | "exclude_persistent">>) =>
    call<SavedArea>(`/me/areas/${id}`, { method: "PATCH", json: patch }),
  deleteArea: (id: number) => call<void>(`/me/areas/${id}`, { method: "DELETE" }),
  adminStats: () => call<Record<string, unknown>>("/admin/stats"),
};
