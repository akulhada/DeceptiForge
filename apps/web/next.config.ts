// Purpose: define Next.js application configuration.
// Responsibilities: transpile the workspace contracts package so the app shares one source of
//   truth for API shapes, and pin the monorepo root so Next/Turbopack do not misinfer it from a
//   stray lockfile (which destabilizes Tailwind's content scan and CSS emission in dev).
// Future modules: add security headers and image rules with their owner.
import { fileURLToPath } from 'node:url';

import type { NextConfig } from 'next';

// apps/web/next.config.ts -> monorepo root is two levels up. Pinning it makes root inference
// deterministic regardless of any package-lock.json outside this pnpm workspace.
const monorepoRoot = fileURLToPath(new URL('../..', import.meta.url));

const nextConfig: NextConfig = {
  transpilePackages: ['@deceptiforge/contracts'],
  outputFileTracingRoot: monorepoRoot,
};

export default nextConfig;
