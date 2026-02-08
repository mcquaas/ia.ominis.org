import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = (process.env.BACKEND_URL || 'http://localhost:8000') + '/v1/api/conversations';

function getAuthHeader(request: NextRequest): Record<string, string> {
  const auth = request.headers.get('Authorization');
  return auth ? { Authorization: auth } : {};
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const res = await fetch(`${BACKEND_URL}/${id}/regenerate-title`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeader(request),
      },
    });

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error('[conversations] regenerate-title error:', error);
    return NextResponse.json({ detail: 'Backend unreachable' }, { status: 502 });
  }
}
