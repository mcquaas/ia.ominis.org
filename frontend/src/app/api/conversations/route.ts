import { NextRequest, NextResponse } from 'next/server';

/**
 * Proxy for conversation CRUD endpoints.
 * Routes through Next.js to avoid CORS issues (same-origin).
 */

const BACKEND_URL = (process.env.BACKEND_URL || 'http://localhost:8000') + '/v1/api/conversations';

function getAuthHeader(request: NextRequest): Record<string, string> {
  const auth = request.headers.get('Authorization');
  return auth ? { Authorization: auth } : {};
}

// GET /api/conversations — list conversations
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const qs = searchParams.toString();
    const url = qs ? `${BACKEND_URL}?${qs}` : BACKEND_URL;

    const res = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeader(request),
      },
    });

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error('[conversations] GET error:', error);
    return NextResponse.json({ detail: 'Backend unreachable' }, { status: 502 });
  }
}

// POST /api/conversations — create conversation
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const res = await fetch(BACKEND_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeader(request),
      },
      body: JSON.stringify(body),
    });

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error('[conversations] POST error:', error);
    return NextResponse.json({ detail: 'Backend unreachable' }, { status: 502 });
  }
}
