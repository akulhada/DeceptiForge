// Purpose: pure, testable state logic for the Analysis Lab route gate.
// Responsibilities: derive the explicit route state from the shared tenant session + API result,
//   build a safe dashboard-connect link that preserves a same-origin return path, and expose the
//   readable dark-theme class constants the empty states use. No React, no DOM, no network.
import type { TenantSession } from './authSession';

export type LabStatus =
  | 'loading'
  | 'unauthenticated'
  | 'no-organization'
  | 'forbidden'
  | 'unavailable'
  | 'ready';

// Roles that carry analysis:preview (server is the authority; this is only a UI hint).
export const ANALYSIS_PREVIEW_ROLES = ['owner', 'admin', 'analyst', 'viewer'] as const;

// Readable classes for the dark security-console theme (no hardcoded black/white/gray).
export const LAB_CARD_CLASS = 'mx-auto mt-10 max-w-lg';
export const LAB_TITLE_CLASS = 'text-slate-100';
export const LAB_BODY_CLASS = 'text-slate-300';
export const LAB_MUTED_CLASS = 'text-slate-400';

/**
 * The state to show before any API call: no session -> unauthenticated; a session without an
 * organization id -> no-organization; otherwise we still need to verify with the API ('loading').
 */
export function preApiStatus(session: TenantSession | null): LabStatus {
  if (session === null) return 'unauthenticated';
  if (!session.organizationId || session.organizationId.trim() === '') return 'no-organization';
  return 'loading';
}

/** Map a failed scenarios/preview call to an explicit state. */
export function statusFromApiError(httpStatus: number): LabStatus {
  if (httpStatus === 401) return 'unauthenticated';
  if (httpStatus === 403) return 'forbidden';
  // 0 = network/unreachable; anything else unexpected is treated as unavailable, not "ready".
  return 'unavailable';
}

/**
 * Keep only a same-origin absolute path as the return target; never trust an arbitrary or
 * protocol-relative value. Defaults to the lab itself.
 */
export function sanitizeReturnPath(path: string | null | undefined): string {
  if (typeof path === 'string' && path.startsWith('/') && !path.startsWith('//')) {
    return path;
  }
  return '/analysis-lab';
}

/** Link to the dashboard connect flow, preserving where to come back to. */
export function buildConnectHref(returnTo: string): string {
  return `/?next=${encodeURIComponent(sanitizeReturnPath(returnTo))}`;
}
