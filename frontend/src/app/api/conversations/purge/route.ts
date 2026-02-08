import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = (process.env.BACKEND_URL || 'http://localhost:8000') + '/v1/api/conversations/purge';

function getAuthHeader(request: NextRequest): Record<string, string> {
  const auth = request.headers.get('Authorization');
  return auth ? { Authorization: auth } : {};
}

// DELETE /api/conversations/purge — delete all conversations
export async function DELETE(request: NextRequest) {
  try {
    const res = await fetch(BACKEND_URL, {
      method: 'DELETE',
      headers: {
        ...getAuthHeader(request),
      },
    });

    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error('[conversations] PURGE error:', error);
    return NextResponse.json({ detail: 'Backend unreachable' }, { status: 502 });
  }
}
