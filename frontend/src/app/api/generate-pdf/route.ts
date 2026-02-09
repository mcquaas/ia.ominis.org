import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 30;

const BACKEND_URL = (process.env.BACKEND_URL || 'http://localhost:8000') + '/v1/generate-pdf';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { content, title } = body;

    if (!content || typeof content !== 'string') {
      return NextResponse.json({ detail: 'Content is required' }, { status: 400 });
    }

    const response = await fetch(BACKEND_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, title: title || 'OMINIS Report' }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Backend error' }));
      return NextResponse.json(error, { status: response.status });
    }

    const pdfBlob = await response.blob();
    const disposition = response.headers.get('Content-Disposition');
    const filenameMatch = disposition?.match(/filename="([^"]+)"/);
    const filename = filenameMatch?.[1] || 'ominis-report.pdf';

    return new NextResponse(pdfBlob, {
      status: 200,
      headers: {
        'Content-Type': 'application/pdf',
        'Content-Disposition': `attachment; filename="${filename}"`,
      },
    });
  } catch (error) {
    console.error('[generate-pdf] Error:', error);
    return NextResponse.json({ detail: 'Failed to generate PDF' }, { status: 500 });
  }
}
