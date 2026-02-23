import { NextRequest } from 'next/server';

export const dynamic = 'force-dynamic';

const MODELS_API = (process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') + '/v1/models';

/**
 * Proxy GET /v1/models so the frontend can send the auth token (same-origin).
 * Backend returns models with allowed/reason per model based on optional user.
 */
export async function GET(request: NextRequest) {
  try {
    const headers: Record<string, string> = {};
    const auth = request.headers.get('Authorization');
    if (auth) headers['Authorization'] = auth;

    const response = await fetch(MODELS_API, { headers });
    const data = await response.json().catch(() => ({}));
    return Response.json(data, { status: response.status });
  } catch (e) {
    console.error('[api/models]', e);
    return Response.json({ models: [], default: 'ominis-2.0' }, { status: 200 });
  }
}
