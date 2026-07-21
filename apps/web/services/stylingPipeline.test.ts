// Purpose: guard the frontend styling pipeline against the failure that rendered the app with
//   browser-default styles — a stray lockfile making Next misinfer the workspace root, plus any
//   Tailwind v3/v4 config drift or a lost global CSS import. File-content checks (node env).
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

// vitest runs from apps/web.
const WEB = process.cwd();
const REPO = resolve(WEB, '..', '..');
const read = (p: string) => readFileSync(resolve(WEB, p), 'utf8');

describe('global stylesheet import', () => {
  it('the root layout imports the global stylesheet exactly once', () => {
    const layout = read('app/layout.tsx');
    const imports = layout.match(/import\s+['"][^'"]*globals\.css['"]/g) ?? [];
    expect(imports).toHaveLength(1);
  });

  it('globals.css applies theme-aware body colors (readable on the dark background)', () => {
    const css = read('styles/globals.css');
    expect(css).toMatch(/bg-slate-950/);
    expect(css).toMatch(/text-slate-200/);
  });
});

describe('Tailwind v4 pipeline consistency (no v3/v4 mismatch)', () => {
  it('installed tailwindcss is v4', () => {
    const pkg = JSON.parse(read('package.json'));
    const version = pkg.devDependencies?.tailwindcss ?? pkg.dependencies?.tailwindcss ?? '';
    expect(version).toMatch(/\^?4\./);
  });

  it('postcss uses the v4 plugin @tailwindcss/postcss', () => {
    const postcss = read('postcss.config.mjs');
    expect(postcss).toContain('@tailwindcss/postcss');
    // v3 plugin name must not linger.
    expect(postcss).not.toMatch(/['"]tailwindcss['"]\s*:/);
  });

  it('globals.css uses the v4 @import, not v3 @tailwind directives', () => {
    const css = read('styles/globals.css');
    expect(css).toMatch(/@import\s+['"]tailwindcss['"]/);
    expect(css).not.toMatch(/@tailwind\s+(base|components|utilities)/);
  });
});

describe('workspace-root determinism', () => {
  it('next.config pins outputFileTracingRoot so root inference is deterministic', () => {
    const config = read('next.config.ts');
    expect(config).toContain('outputFileTracingRoot');
  });

  it('no stray non-pnpm lockfile at the repo root (would misdirect root inference)', () => {
    expect(existsSync(resolve(REPO, 'package-lock.json'))).toBe(false);
    expect(existsSync(resolve(REPO, 'yarn.lock'))).toBe(false);
    expect(existsSync(resolve(REPO, 'pnpm-lock.yaml'))).toBe(true);
  });
});

describe('no page-level emergency inline styling', () => {
  it('analysis-lab + layout do not hardcode inline color/background styles', () => {
    for (const file of ['components/analysis-lab/AnalysisLab.tsx', 'app/layout.tsx']) {
      const src = read(file);
      // Allow dynamic width for meters; forbid inline color/background emergency hacks.
      expect(src).not.toMatch(/style=\{\{[^}]*(color|background)[^}]*\}\}/);
    }
  });
});
