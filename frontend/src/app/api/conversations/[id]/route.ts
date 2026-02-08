import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = (process.env.BACKEND_URL || 'http://localhost:8000') + '/v1/api/conversations';

function getAuthHeader(request: NextRequest): Record<string, string> {
  const auth = request.headers.get('Authorization');
  return auth ? { Authorization: auth } : {};
}

// GET /api/conversations/[id] — get conversation with messages
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const res = await fetch(`${BACKEND_URL}/${id}`, {
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeader(request),
      },
    });

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error('[conversations] GET by id error:', error);
    return NextResponse.json({ detail: 'Backend unreachable' }, { status: 502 });
  }
}

// PUT /api/conversations/[id] — update conversation (rename, toggle saved)
export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const body = await request.json();

    const res = await fetch(`${BACKEND_URL}/${id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeader(request),
      },
      body: JSON.stringify(body),
    });

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error('[conversations] PUT error:', error);
    return NextResponse.json({ detail: 'Backend unreachable' }, { status: 502 });
  }
}

// DELETE /api/conversations/[id] — delete conversation
export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const res = await fetch(`${BACKEND_URL}/${id}`, {
      method: 'DELETE',
      headers: {
        ...getAuthHeader(request),
      },
    });

    if (res.status === 204) {
      return new NextResponse(null, { status: 204 });
    }

    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error('[conversations] DELETE error:', error);
    return NextResponse.json({ detail: 'Backend unreachable' }, { status: 502 });
  }
}
