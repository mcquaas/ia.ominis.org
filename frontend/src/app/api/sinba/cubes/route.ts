import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

/**
 * GET /api/sinba/cubes — List all available SINBA cubes
 */
export async function GET() {
  try {
    const response = await fetch(`${BACKEND_URL}/v1/sinba/cubes`);
    if (!response.ok) throw new Error(`Backend error: ${response.status}`);
    return NextResponse.json(await response.json());
  } catch (error) {
    console.error('SINBA cubes list error:', error);
    return NextResponse.json({ error: 'Failed to list SINBA cubes' }, { status: 500 });
  }
}
