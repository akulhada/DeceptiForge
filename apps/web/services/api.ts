// Purpose: single typed client for the DeceptiForge demo API.
// Responsibilities: centralize base URL, request handling, and error normalization so components
//   never call fetch directly. Dependencies: the demo payload types.
import type { DemoState } from './types';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      cache: 'no-store',
      headers: { 'content-type': 'application/json', ...init?.headers },
    });
  } catch {
    throw new ApiError(`Cannot reach the API at ${BASE_URL}. Is it running?`, 0);
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body && typeof body.detail === 'string'
        ? body.detail
        : `Request to ${path} failed (${response.status}).`;
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export const api = {
  getState: () => request<DemoState>('/demo/state'),
  seed: () => request<DemoState>('/demo/seed', { method: 'POST' }),
  simulateDetection: () => request<DemoState>('/demo/simulate-detection', { method: 'POST' }),
};
