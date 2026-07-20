// Purpose: irreversible hashing helpers using Web Crypto.
// Responsibilities: SHA-256 hex of a string. Used to fingerprint candidate markers locally so the
//   raw marker is never shipped, and to hash an optional local excerpt. No secrets handled here.

export async function sha256Hex(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
