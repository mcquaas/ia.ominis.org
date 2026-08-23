import { NextRequest } from 'next/server';

export const dynamic = 'force-dynamic';

const BACKEND = (process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '');
const TARGET = `${BACKEND}/v1/api/system-stats/query-series`;

/**
 * Proxy query time-series so the browser calls same-origin /api/... (BACKEND_URL on server).
 */
export async function GET(request: NextRequest) {
  try {
    const headers: Record<string, string> = { Accept: 'application/json' };
    const auth = request.headers.get('Authorization');
    if (auth) headers['Authorization'] = auth;

    const response = await fetch(TARGET, { headers, cache: 'no-store' });
    const text = await response.text();
    let data: unknown;
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { detail: text.slice(0, 500) || 'Invalid response from backend' };
    }
    return Response.json(data, { status: response.status });
  } catch (e) {
    console.error('[api/system-stats/query-series]', e);
    return Response.json({ detail: 'Proxy error' }, { status: 502 });
  }
}
