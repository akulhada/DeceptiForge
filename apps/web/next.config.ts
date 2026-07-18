// Purpose: define Next.js application configuration.
// Responsibilities: transpile the workspace contracts package so the app shares one source of
//   truth for API shapes. Future modules: add security headers and image rules with their owner.
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  transpilePackages: ['@deceptiforge/contracts'],
};

export default nextConfig;
