// Purpose: the security-header contract must not silently weaken.
// These assert the policy the app emits. They do NOT prove a deployed proxy preserves the headers —
// that requires testing the real ingress, which no configuration in this repository provides.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const WEB = process.cwd();
const middleware = readFileSync(resolve(WEB, 'middleware.ts'), 'utf8');
const config = readFileSync(resolve(WEB, 'next.config.ts'), 'utf8');

describe('content security policy', () => {
  it('does not allow inline or eval scripts outside development', () => {
    // `next dev` needs eval for HMR, so development relaxes script-src. Assert the PRODUCTION
    // branch specifically — matching the first script-src in the file would now match the dev one
    // and make this guard hollow.
    const production = /return `script-src 'self' 'nonce-\$\{nonce\}'[^`]*`/.exec(middleware)?.[0];
    expect(production, 'production script-src not found').toBeTruthy();
    expect(production).not.toContain("'unsafe-inline'");
    expect(production).not.toContain("'unsafe-eval'");
    expect(production).toContain("'strict-dynamic'");
  });

  it('gates the development relaxation on NODE_ENV', () => {
    // If this were not gated, a production build would ship eval-enabled scripts.
    expect(middleware).toContain("process.env.NODE_ENV === 'development'");
    const dev = /if \(IS_DEV\) \{[\s\S]*?\}/.exec(middleware)?.[0] ?? '';
    expect(dev).toContain("'unsafe-eval'");
  });

  it('uses a per-request nonce rather than a static allow-list', () => {
    expect(middleware).toContain("'nonce-${nonce}'");
    expect(middleware).toContain('crypto.randomUUID');
  });

  it('denies framing, plugins and arbitrary base URIs', () => {
    expect(middleware).toContain("frame-ancestors 'none'");
    expect(middleware).toContain("object-src 'none'");
    expect(middleware).toContain("base-uri 'self'");
  });

  it('restricts where the browser may send data', () => {
    // An injected script must not be able to post the session API key to another origin.
    expect(middleware).toContain('connect-src');
    expect(middleware).toContain('NEXT_PUBLIC_API_URL');
    expect(middleware).toContain("default-src 'self'");
  });
});

describe('static security headers', () => {
  it.each([
    ['X-Content-Type-Options', 'nosniff'],
    ['X-Frame-Options', 'DENY'],
    ['Referrer-Policy', 'strict-origin-when-cross-origin'],
    ['Permissions-Policy', 'camera=()'],
    ['Strict-Transport-Security', 'max-age=31536000'],
  ])('sets %s', (header, value) => {
    expect(config).toContain(header);
    expect(config).toContain(value);
  });

  it('applies them to every path', () => {
    expect(config).toContain("source: '/:path*'");
  });
});
