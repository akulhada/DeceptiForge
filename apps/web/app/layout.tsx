// Purpose: define the Next.js root document shell.
// Responsibilities: load global styles, provide application metadata, and read the per-request CSP
//   nonce so Next can stamp it onto its own bootstrap scripts.
// Future modules: add providers only when shared client state or data fetching requires them.
import type { Metadata } from 'next';
import { headers } from 'next/headers';
import type { ReactNode } from 'react';

import '../styles/globals.css';

export const metadata: Metadata = {
  title: 'DeceptiForge',
  description: 'Context-aware deception platform for AI-era security.',
};

// Reading a request header opts every route out of static prerendering, and that is the point.
// A statically prerendered page is built ONCE with no nonce, while the middleware sends a fresh
// per-request `script-src 'nonce-…' 'strict-dynamic'`. Under strict-dynamic a nonce is the only
// thing that authorises a script — 'self' no longer helps — so a prerendered page has every one of
// its scripts blocked and never hydrates. Rendering per request lets Next apply the matching nonce.
export const dynamic = 'force-dynamic';

export default async function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  // The value is unused here; requesting it is what makes the render dynamic and hands Next the
  // nonce to stamp. Keep this call even though nothing reads the result.
  await headers();
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
