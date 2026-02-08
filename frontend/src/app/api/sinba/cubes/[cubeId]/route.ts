import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

/**
 * GET /api/sinba/cubes/[cubeId] — Get metadata for a specific cube
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ cubeId: string }> }
) {
  try {
    const { cubeId } = await params;
    const response = await fetch(`${BACKEND_URL}/v1/sinba/cubes/${encodeURIComponent(cubeId)}`);
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Not found' }));
      return NextResponse.json(err, { status: response.status });
    }
    return NextResponse.json(await response.json());
  } catch (error) {
    console.error('SINBA cube metadata error:', error);
    return NextResponse.json({ error: 'Failed to get cube metadata' }, { status: 500 });
  }
}
