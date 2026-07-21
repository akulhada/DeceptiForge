// Purpose: the frontend route model — which surfaces a build exposes, and what the nav may show.
// These mirror the backend deployment-mode tests. If the two ever disagree, a route is either
// advertised and unreachable, or reachable and unadvertised.
import { describe, expect, it } from 'vitest';

import {
  analysisLabEnabled,
  demoEnabled,
  deploymentMode,
  judgeWorkspaceEnabled,
  navigationFor,
} from './deploymentMode';

describe('deploymentMode', () => {
  it('resolves each known mode', () => {
    for (const mode of ['development', 'test', 'judge', 'staging', 'production'] as const) {
      expect(deploymentMode(mode)).toBe(mode);
    }
  });

  it('falls back to the most restrictive mode, never the most permissive', () => {
    // A typo or an unset variable must hide demonstration surfaces, not reveal them.
    expect(deploymentMode(undefined)).toBe('production');
    expect(deploymentMode('')).toBe('production');
    expect(deploymentMode('prod')).toBe('production');
    expect(deploymentMode('DEVELOPMENT')).toBe('production');
  });
});

describe('demo surface', () => {
  it.each(['development', 'judge'] as const)('is available in %s with the flag', (mode) => {
    expect(demoEnabled(mode, 'true')).toBe(true);
  });

  it.each(['development', 'judge'] as const)('still requires the flag in %s', (mode) => {
    expect(demoEnabled(mode, undefined)).toBe(false);
    expect(demoEnabled(mode, 'false')).toBe(false);
  });

  it.each(['test', 'staging', 'production'] as const)('is never available in %s', (mode) => {
    expect(demoEnabled(mode, 'true')).toBe(false);
  });
});

describe('judge workspace', () => {
  it.each(['development', 'judge'] as const)('is available in %s with the flag', (mode) => {
    expect(judgeWorkspaceEnabled(mode, 'true')).toBe(true);
  });

  it.each(['test', 'staging', 'production'] as const)('is never available in %s', (mode) => {
    expect(judgeWorkspaceEnabled(mode, 'true')).toBe(false);
  });
});

describe('analysis lab', () => {
  it.each(['development', 'test'] as const)('is available in %s with the flag', (mode) => {
    expect(analysisLabEnabled(mode, 'true')).toBe(true);
  });

  it.each(['judge', 'staging', 'production'] as const)(
    'is unavailable in %s even with the flag set',
    (mode) => {
      // The route calls this and returns a real 404, so the lab is absent rather than merely
      // missing from the navigation.
      expect(analysisLabEnabled(mode, 'true')).toBe(false);
    },
  );
});

describe('navigation', () => {
  it('offers a hosted judge the demo and their workspace, and nothing else', () => {
    process.env.NEXT_PUBLIC_DEMO_MODE = 'true';
    process.env.NEXT_PUBLIC_JUDGE_WORKSPACE_ENABLED = 'true';
    process.env.NEXT_PUBLIC_ANALYSIS_LAB_ENABLED = 'true';
    try {
      const items = navigationFor('judge');
      expect(items.map((i) => i.href)).toEqual(['/demo', '/']);
      // The Analysis Lab must not be advertised to a judge even when the flag is set.
      expect(items.some((i) => i.href === '/analysis-lab')).toBe(false);
    } finally {
      delete process.env.NEXT_PUBLIC_DEMO_MODE;
      delete process.env.NEXT_PUBLIC_JUDGE_WORKSPACE_ENABLED;
      delete process.env.NEXT_PUBLIC_ANALYSIS_LAB_ENABLED;
    }
  });

  it('advertises nothing in production', () => {
    process.env.NEXT_PUBLIC_DEMO_MODE = 'true';
    process.env.NEXT_PUBLIC_JUDGE_WORKSPACE_ENABLED = 'true';
    try {
      expect(navigationFor('production')).toEqual([]);
    } finally {
      delete process.env.NEXT_PUBLIC_DEMO_MODE;
      delete process.env.NEXT_PUBLIC_JUDGE_WORKSPACE_ENABLED;
    }
  });

  it('never advertises administration, platform controls or connectors', () => {
    process.env.NEXT_PUBLIC_DEMO_MODE = 'true';
    process.env.NEXT_PUBLIC_JUDGE_WORKSPACE_ENABLED = 'true';
    try {
      const hrefs = navigationFor('judge').map((i) => i.href);
      for (const forbidden of ['/admin', '/platform', '/connectors', '/tenants', '/judge']) {
        expect(hrefs).not.toContain(forbidden);
      }
    } finally {
      delete process.env.NEXT_PUBLIC_DEMO_MODE;
      delete process.env.NEXT_PUBLIC_JUDGE_WORKSPACE_ENABLED;
    }
  });
});
