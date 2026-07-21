// Purpose: verify the Analysis Lab route-state logic — state derivation for every gate case,
//   safe return-path handling, the connect-link builder, the permission-role hint, and that the
//   empty-state class constants are dark-theme readable (no hardcoded black/white/gray).
import { describe, expect, it } from 'vitest';

import type { TenantSession } from './authSession';
import {
  ANALYSIS_PREVIEW_ROLES,
  buildConnectHref,
  LAB_BODY_CLASS,
  LAB_MUTED_CLASS,
  LAB_TITLE_CLASS,
  preApiStatus,
  sanitizeReturnPath,
  statusFromApiError,
} from './analysisLabState';

const SESSION: TenantSession = {
  baseUrl: 'https://api.example.com',
  organizationId: '00000000-0000-0000-0000-000000000001',
  apiKey: 'dfk_secret',
};

describe('preApiStatus', () => {
  it('unauthenticated when there is no session', () => {
    expect(preApiStatus(null)).toBe('unauthenticated');
  });

  it('no-organization when the session lacks an organization id', () => {
    expect(preApiStatus({ ...SESSION, organizationId: '' })).toBe('no-organization');
    expect(preApiStatus({ ...SESSION, organizationId: '   ' })).toBe('no-organization');
  });

  it('loading (needs API verification) when session + organization are present', () => {
    expect(preApiStatus(SESSION)).toBe('loading');
  });
});

describe('statusFromApiError', () => {
  it('maps 401 to unauthenticated', () => {
    expect(statusFromApiError(401)).toBe('unauthenticated');
  });
  it('maps 403 to forbidden (no analysis:preview)', () => {
    expect(statusFromApiError(403)).toBe('forbidden');
  });
  it('maps network (0) and unexpected codes to unavailable, never ready', () => {
    expect(statusFromApiError(0)).toBe('unavailable');
    expect(statusFromApiError(500)).toBe('unavailable');
  });
});

describe('sanitizeReturnPath', () => {
  it('keeps a same-origin absolute path', () => {
    expect(sanitizeReturnPath('/analysis-lab')).toBe('/analysis-lab');
  });
  it('rejects protocol-relative and external targets', () => {
    expect(sanitizeReturnPath('//evil.example.com')).toBe('/analysis-lab');
    expect(sanitizeReturnPath('https://evil.example.com')).toBe('/analysis-lab');
    expect(sanitizeReturnPath('javascript:alert(1)')).toBe('/analysis-lab');
    expect(sanitizeReturnPath(null)).toBe('/analysis-lab');
  });
});

describe('buildConnectHref', () => {
  it('links to the dashboard preserving an encoded return path', () => {
    expect(buildConnectHref('/analysis-lab')).toBe('/?next=%2Fanalysis-lab');
  });
  it('does not carry an unsafe return path', () => {
    expect(buildConnectHref('//evil')).toBe('/?next=%2Fanalysis-lab');
  });
});

describe('permission hint', () => {
  it('lists exactly the roles that carry analysis:preview (no sensors)', () => {
    expect([...ANALYSIS_PREVIEW_ROLES]).toEqual(['owner', 'admin', 'analyst', 'viewer']);
    expect(ANALYSIS_PREVIEW_ROLES).not.toContain('agent_sensor');
    expect(ANALYSIS_PREVIEW_ROLES).not.toContain('service');
  });
});

describe('dark-theme contrast classes', () => {
  it('use readable slate tokens, never hardcoded black/white/gray', () => {
    for (const cls of [LAB_TITLE_CLASS, LAB_BODY_CLASS, LAB_MUTED_CLASS]) {
      expect(cls).toMatch(/text-slate-(100|200|300|400)/);
      expect(cls).not.toMatch(/text-black|bg-white|text-gray-900|text-gray-800/);
    }
  });
});
