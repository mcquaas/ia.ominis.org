import { NextRequest } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300; // research can take longer (ominis-2.0 deep research)

/**
 * Modo Investigación — ominis-2.0 pipeline.
 * Deterministic routing: research mode always uses ominis-2.0 (academic LLM).
 */
const ACADEMIC_API = (process.env.BACKEND_URL || 'http://localhost:8000') + '/v1/academic_query-stream';

export async function POST(request: NextRequest) {
  const encoder = new TextEncoder();
  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();

  (async () => {
    try {
      const body = await request.json();

      const apiBody = {
        question: body.question,
        history: body.history,
        image: body.images && body.images.length > 0 ? body.images[0] : undefined,
        model: body.model || undefined,
        research_model: body.research_model || undefined,
        rag_search: body.rag_search !== false,
        web_search: body.web_search !== false,
        pubmed_search: body.pubmed_search !== false,
        openscholar_search: body.openscholar_search === true,
        file_context: body.file_context || undefined,
        iterations: body.iterations || 4,
        max_total_sources: body.max_total_sources || 30,
        max_follow_links: body.max_follow_links || 8,
        max_trusted_sources: body.max_trusted_sources || 8,
        time_budget_seconds: body.time_budget_seconds || 180,
        excluded_sources: body.excluded_sources || [],
      };

      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      const auth = request.headers.get('Authorization');
      if (auth) headers['Authorization'] = auth;

      const response = await fetch(ACADEMIC_API, {
        method: 'POST',
        headers,
        body: JSON.stringify(apiBody),
      });

      if (!response.ok) {
        let message = `Academic API error: ${response.status}`;
        let reason: string | undefined;
        try {
          const errBody = await response.json();
          if (errBody?.detail?.code === 'model_not_allowed' && errBody?.detail?.reason === 'login_required') {
            reason = 'login_required';
            message = 'Inicia sesión para usar el modo Investigación.';
          }
        } catch {
          // ignore
        }
        const errorEvent = `data: ${JSON.stringify({ type: 'error', message, reason: reason ?? null })}\n\n`;
        await writer.write(encoder.encode(errorEvent));
        await writer.close();
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        const errorEvent = `data: ${JSON.stringify({ type: 'error', message: 'No response body' })}\n\n`;
        await writer.write(encoder.encode(errorEvent));
        await writer.close();
        return;
      }

      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        await writer.write(encoder.encode(chunk));
      }

      await writer.close();
    } catch (error: unknown) {
      const err = error as Error & { code?: string };
      console.error('[academic-query-stream] Error:', err?.message || err, 'code=', (err as Error & { code?: string }).code, 'BACKEND_URL=', (process.env.BACKEND_URL || '').replace(/\d+\.\d+\.\d+\.\d+/, '***'));
      const reason = err?.code === 'ECONNREFUSED' ? 'Backend no disponible (ECONNREFUSED)' : err?.code === 'ETIMEDOUT' ? 'Timeout al conectar con el backend' : err?.message || 'Connection error';
      const errorEvent = `data: ${JSON.stringify({ type: 'error', message: reason })}\n\n`;
      try {
        await writer.write(encoder.encode(errorEvent));
        await writer.close();
      } catch {
        // Writer may already be closed
      }
    }
  })();

  return new Response(readable, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  });
}

export async function OPTIONS() {
  return new Response(null, {
    status: 200,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    },
  });
}
