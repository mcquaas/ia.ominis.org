import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const BACKEND_URL = (process.env.BACKEND_URL || 'http://localhost:8000') + '/v1/extract-file';

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get('file');

    if (!file || !(file instanceof Blob)) {
      return NextResponse.json({ detail: 'No file provided' }, { status: 400 });
    }

    const backendForm = new FormData();
    backendForm.append('file', file);

    const response = await fetch(BACKEND_URL, {
      method: 'POST',
      body: backendForm,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Backend error' }));
      return NextResponse.json(error, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('[extract-file] Error:', error);
    return NextResponse.json({ detail: 'Failed to extract file content' }, { status: 500 });
  }
}
