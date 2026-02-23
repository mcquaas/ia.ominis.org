import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = (process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '');
const LOGIN_ENDPOINT = `${BACKEND_URL}/v1/api/auth/local`;

export const dynamic = 'force-dynamic';

/** Fail fast so the client gets a 502 instead of waiting for client timeout. */
const BACKEND_TIMEOUT_MS = 10_000;

/**
 * Proxy login to the Haystack backend (api.ominis.org). Same-origin request avoids CORS;
 * server uses BACKEND_URL to reach the backend.
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), BACKEND_TIMEOUT_MS);
    const res = await fetch(LOGIN_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      return NextResponse.json(
        { detail: typeof data?.detail === 'string' ? data.detail : 'Invalid identifier or password' },
        { status: res.status }
      );
    }
    return NextResponse.json(data);
  } catch (e) {
    const isAbort = e instanceof Error && e.name === 'AbortError';
    const message = isAbort
      ? `El backend (${BACKEND_URL}) no respondió en ${BACKEND_TIMEOUT_MS / 1000}s. Comprueba que esté activo.`
      : (e instanceof Error ? e.message : 'No se pudo conectar al backend.');
    return NextResponse.json(
      { detail: message },
      { status: 502 }
    );
  }
}
