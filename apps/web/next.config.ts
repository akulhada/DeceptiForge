// Purpose: define Next.js application configuration.
// Responsibilities: transpile the workspace contracts package so the app shares one source of
//   truth for API shapes, and pin the monorepo root so Next/Turbopack do not misinfer it from a
//   stray lockfile (which destabilizes Tailwind's content scan and CSS emission in dev).
// Security headers are set here for everything that is not per-request; the per-request CSP with
//   its script nonce lives in middleware.ts.
import { fileURLToPath } from 'node:url';

import type { NextConfig } from 'next';

// apps/web/next.config.ts -> monorepo root is two levels up. Pinning it makes root inference
// deterministic regardless of any package-lock.json outside this pnpm workspace.
const monorepoRoot = fileURLToPath(new URL('../..', import.meta.url));

// Applied to every response. These are static, so they belong here rather than in middleware.
// NOTE: an ingress or CDN in front of this app must PRESERVE these headers, and must re-add them if
// it terminates and regenerates responses. Verifying next.config.ts alone does not prove the
// deployed edge preserves them — see docs/ProductionReadiness.md.
const SECURITY_HEADERS = [
  // Defense in depth alongside CSP frame-ancestors, for agents that predate it.
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  // Deny powerful features the dashboard never uses.
  {
    key: 'Permissions-Policy',
    value: 'camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()',
  },
  // Only meaningful over HTTPS; harmless on plain HTTP where browsers ignore it.
  { key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' },
];

const nextConfig: NextConfig = {
  transpilePackages: ['@deceptiforge/contracts'],
  outputFileTracingRoot: monorepoRoot,
  // Headers are emitted by the app itself so a misconfigured proxy cannot silently drop all
  // protection; the proxy is expected to preserve, not to be the only source.
  async headers() {
    return [{ source: '/:path*', headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;
