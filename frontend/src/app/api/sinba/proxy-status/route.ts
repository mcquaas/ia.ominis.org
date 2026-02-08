import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

/**
 * GET /api/sinba/proxy-status — Check if the XMLA proxy is reachable
 */
export async function GET() {
  try {
    const response = await fetch(`${BACKEND_URL}/v1/sinba/proxy-status`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(5000),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.ok ? 200 : 503 });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Proxy status check failed';
    return NextResponse.json(
      { healthy: false, error: message },
      { status: 503 }
    );
  }
}
