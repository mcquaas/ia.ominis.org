import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = (process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(
  /\/$/,
  ''
);
const BASE = `${BACKEND_URL}/v1/api/api-keys`;

export const dynamic = 'force-dynamic';

const BACKEND_TIMEOUT_MS = 30_000;

async function forward(init: RequestInit & { url: string }): Promise<NextResponse> {
  const { url, ...rest } = init;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), BACKEND_TIMEOUT_MS);
  try {
    const res = await fetch(url, { ...rest, signal: controller.signal });
    clearTimeout(timeoutId);
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    clearTimeout(timeoutId);
    const isAbort = e instanceof Error && e.name === 'AbortError';
    const message = isAbort
      ? `El backend (${BACKEND_URL}) no respondió en ${BACKEND_TIMEOUT_MS / 1000}s.`
      : e instanceof Error
        ? e.message
        : 'No se pudo conectar al backend.';
    return NextResponse.json({ detail: message }, { status: 502 });
  }
}

/**
 * Proxy API key list/create to Haystack. Same-origin + server BACKEND_URL so keys
 * are always stored on the same database as the rest of the proxied API (matches /api/auth/login).
 */
export async function GET(request: NextRequest) {
  const auth = request.headers.get('authorization');
  if (!auth) {
    return NextResponse.json({ detail: 'Authentication required' }, { status: 401 });
  }
  const q = request.nextUrl.search;
  return forward({
    url: `${BASE}${q}`,
    method: 'GET',
    headers: { Authorization: auth },
  });
}

export async function POST(request: NextRequest) {
  const auth = request.headers.get('authorization');
  if (!auth) {
    return NextResponse.json({ detail: 'Authentication required' }, { status: 401 });
  }
  const body = await request.text();
  return forward({
    url: BASE,
    method: 'POST',
    headers: {
      Authorization: auth,
      'Content-Type': 'application/json',
    },
    body: body || '{}',
  });
}
