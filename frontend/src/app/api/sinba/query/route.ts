import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

/**
 * POST /api/sinba/query — Query a SINBA cube with natural language or MDX
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120_000); // 2 min max

    const response = await fetch(`${BACKEND_URL}/v1/sinba/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: request.headers.get('Authorization') || '',
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    clearTimeout(timeout);
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error('SINBA query error:', error);
    const message =
      error instanceof Error
        ? error.name === 'AbortError'
          ? 'Tiempo de espera agotado. El proxy o SSAS pueden no estar disponibles.'
          : error.message
        : 'Error al consultar el cubo SINBA';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
