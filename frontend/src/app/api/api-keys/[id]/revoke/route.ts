import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = (process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(
  /\/$/,
  ''
);

export const dynamic = 'force-dynamic';

const BACKEND_TIMEOUT_MS = 30_000;

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ id: string }> }
) {
  const auth = request.headers.get('authorization');
  if (!auth) {
    return NextResponse.json({ detail: 'Authentication required' }, { status: 401 });
  }
  const { id } = await context.params;
  const url = `${BACKEND_URL}/v1/api/api-keys/${encodeURIComponent(id)}/revoke`;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), BACKEND_TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { Authorization: auth, 'Content-Type': 'application/json' },
      body: '{}',
      signal: controller.signal,
    });
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
