// Purpose: emit a per-request Content-Security-Policy with a script nonce.
// Responsibilities: generate a fresh nonce per response, build a CSP that does NOT rely on
//   'unsafe-inline' for scripts, and pass the nonce to Next so its own bootstrap scripts are
//   allowed. This matters here specifically: the dashboard holds a tenant API key in
//   sessionStorage, so a single injected script would be enough to exfiltrate it.
// Dependencies: next/server only.
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// The API the browser is allowed to call. Anything else is refused by connect-src, so an injected
// script cannot post a stolen key to an attacker-controlled origin.
const API_ORIGIN = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// `next dev` serves its HMR and React Refresh runtime through eval, and emits its inline bootstrap
// scripts with an EMPTY nonce attribute. Under the production policy they are all refused, so the
// page server-renders and then never hydrates — silently, with no console error.
//
// The development policy therefore carries NO nonce at all. This matters more than it looks: a CSP
// that contains a nonce makes the browser IGNORE 'unsafe-inline' entirely, so listing both would
// leave Next's nonce="" inline scripts blocked exactly as before. Dropping the nonce is what makes
// 'unsafe-inline' take effect.
const IS_DEV = process.env.NODE_ENV === 'development';

function scriptSrc(nonce: string): string {
  if (IS_DEV) {
    return "script-src 'self' 'unsafe-eval' 'unsafe-inline'";
  }
  // 'strict-dynamic' lets Next's nonced bootstrap load its own chunks without allowing arbitrary
  // hosts. No 'unsafe-inline' and no 'unsafe-eval'.
  return `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`;
}

function buildPolicy(nonce: string): string {
  return [
    "default-src 'self'",
    scriptSrc(nonce),
    // Styles remain 'unsafe-inline': Next injects inline style attributes and there is no nonce
    // channel for them. Style injection is materially less dangerous than script execution, and
    // script-src above is what protects the session key.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src 'self' ${API_ORIGIN}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    // Clickjacking protection. frame-ancestors is the modern control; X-Frame-Options in
    // next.config.ts covers agents that predate it.
    "frame-ancestors 'none'",
    'upgrade-insecure-requests',
  ].join('; ');
}

export function middleware(request: NextRequest) {
  const nonce = crypto.randomUUID().replace(/-/g, '');
  const policy = buildPolicy(nonce);

  // Next reads x-nonce to stamp its own script tags.
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set('x-nonce', nonce);
  requestHeaders.set('Content-Security-Policy', policy);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set('Content-Security-Policy', policy);
  return response;
}

export const config = {
  // Apply to documents, not to static assets or image optimization, which need no policy and would
  // only pay the cost.
  matcher: [
    {
      source: '/((?!_next/static|_next/image|favicon.ico).*)',
      missing: [
        { type: 'header', key: 'next-router-prefetch' },
        { type: 'header', key: 'purpose', value: 'prefetch' },
      ],
    },
  ],
};
