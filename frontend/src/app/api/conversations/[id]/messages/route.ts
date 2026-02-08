import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = (process.env.BACKEND_URL || 'http://localhost:8000') + '/v1/api/conversations';

function getAuthHeader(request: NextRequest): Record<string, string> {
  const auth = request.headers.get('Authorization');
  return auth ? { Authorization: auth } : {};
}

// POST /api/conversations/[id]/messages — add messages to conversation
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const body = await request.json();

    const res = await fetch(`${BACKEND_URL}/${id}/messages`, {
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
    console.error('[conversations] POST messages error:', error);
    return NextResponse.json({ detail: 'Backend unreachable' }, { status: 502 });
  }
}
