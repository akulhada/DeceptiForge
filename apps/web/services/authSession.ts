// Purpose: hold the staging tenant connection (base URL, organization id, API key).
// Responsibilities: keep credentials only in sessionStorage/memory — never in NEXT_PUBLIC build
//   variables — and expose get/set/clear. The API key is a staging secret; treat it as sensitive.
// Note on lifetime: sessionStorage is per-tab but NOT memory-only. Browsers persist it and restore
//   it on session restore or tab duplication, so it can outlive the visible session. UI copy must
//   not promise that closing the window destroys the key. Any script on this origin can also read
//   it, which is why the CSP in middleware.ts forbids inline and third-party scripts.
'use client';

export interface TenantSession {
  readonly baseUrl: string;
  readonly organizationId: string;
  readonly apiKey: string;
}

const STORAGE_KEY = 'deceptiforge.tenant-session';

let memorySession: TenantSession | null = null;

export function getSession(): TenantSession | null {
  if (memorySession) return memorySession;
  if (typeof window === 'undefined') return null;
  const raw = window.sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    memorySession = JSON.parse(raw) as TenantSession;
    return memorySession;
  } catch {
    return null;
  }
}

export function setSession(session: TenantSession): void {
  memorySession = session;
  if (typeof window !== 'undefined') {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  }
}

export function clearSession(): void {
  memorySession = null;
  if (typeof window !== 'undefined') {
    window.sessionStorage.removeItem(STORAGE_KEY);
  }
}
