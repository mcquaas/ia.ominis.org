import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

/**
 * GET /api/sinba/catalog — Discover and catalog all SINBA cubes
 */
export async function GET(request: NextRequest) {
  try {
    const maxCubes = request.nextUrl.searchParams.get('max_cubes') || '0';
    const response = await fetch(`${BACKEND_URL}/v1/sinba/catalog?max_cubes=${maxCubes}`);
    if (!response.ok) throw new Error(`Backend error: ${response.status}`);
    return NextResponse.json(await response.json());
  } catch (error) {
    console.error('SINBA catalog error:', error);
    return NextResponse.json({ error: 'Failed to catalog SINBA cubes' }, { status: 500 });
  }
}
