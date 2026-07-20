// Purpose: sign browser event requests with the sensor's scoped secret (monitor-signature-v1).
// Responsibilities: build the exact canonical payload the backend verifies and compute the hex
//   HMAC-SHA256 over it using Web Crypto. The secret stays in the service worker; it is never
//   exposed to page context. No DOM, no network.
const SIGNATURE_VERSION = 'monitor-signature-v1';

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', bytes as BufferSource);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export interface CanonicalInput {
  method: string;
  path: string;
  organizationId: string;
  sensorPublicId: string;
  timestamp: string;
  nonce: string;
  body: string; // exact request body bytes as a UTF-8 string
}

export async function canonicalRequest(input: CanonicalInput): Promise<string> {
  const bodyHash = await sha256Hex(new TextEncoder().encode(input.body));
  return [
    SIGNATURE_VERSION,
    input.method.toUpperCase(),
    input.path,
    input.organizationId,
    input.sensorPublicId,
    input.timestamp,
    input.nonce,
    bodyHash,
  ].join('\n');
}

export async function signRequest(secret: string, canonical: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(canonical));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
