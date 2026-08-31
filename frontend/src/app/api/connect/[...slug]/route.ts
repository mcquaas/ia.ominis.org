import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const BACKEND_URL = (process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'https://api.ominis.org').replace(/\/$/, '');

export async function GET(request: NextRequest, context: { params: Promise<{ slug: string[] }> }) {
  const { slug } = await context.params;
  const path = slug.join('/');
  const query = request.nextUrl.search;
  const backendTarget = `${BACKEND_URL}/v1/api/connect/${path}${query}`;

  try {
    const res = await fetch(backendTarget, {
      method: 'GET',
      headers: {
        cookie: request.headers.get('cookie') || '',
        'user-agent': request.headers.get('user-agent') || '',
        'x-forwarded-proto': 'https',
        'x-forwarded-host': request.headers.get('host') || 'ia.ominis.org',
      },
      redirect: 'manual',
    });

    // If backend returns a redirect (302/301), pass it along to the client
    const location = res.headers.get('location');
    if (location && [301, 302, 303, 307, 308].includes(res.status)) {
      const response = NextResponse.redirect(new URL(location, request.url), {
        status: res.status,
      });

      // Pass through set-cookie headers (e.g. oauth_state)
      const setCookies = res.headers.getSetCookie ? res.headers.getSetCookie() : [res.headers.get('set-cookie')].filter(Boolean);
      for (const cookie of setCookies) {
        if (cookie) response.headers.append('set-cookie', cookie);
      }
      return response;
    }

    const body = await res.arrayBuffer();
    const response = new NextResponse(body, {
      status: res.status,
      headers: {
        'content-type': res.headers.get('content-type') || 'application/json',
      },
    });

    const setCookies = res.headers.getSetCookie ? res.headers.getSetCookie() : [res.headers.get('set-cookie')].filter(Boolean);
    for (const cookie of setCookies) {
      if (cookie) response.headers.append('set-cookie', cookie);
    }
    return response;
  } catch (error) {
    console.error(`[api/connect/${path}] proxy error:`, error);
    return NextResponse.json({ error: 'Backend connection failed' }, { status: 502 });
  }
}
