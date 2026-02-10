import { NextRequest } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 180; // research can take longer

// Modo Investigación: deterministic routing to ominis-2.0 (per architecture)
const RESEARCH_API = (process.env.BACKEND_URL || 'http://localhost:8000') + '/v1/academic_query-stream';

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
        rag_search: body.rag_search !== false,
        web_search: body.web_search !== false,
        pubmed_search: body.pubmed_search !== false,
        file_context: body.file_context || undefined,
        iterations: body.iterations || 4,
        max_total_sources: body.max_total_sources || 30,
        max_follow_links: body.max_follow_links || 8,
        max_trusted_sources: body.max_trusted_sources || 8,
        time_budget_seconds: body.time_budget_seconds || 180,
        excluded_sources: body.excluded_sources || [],
      };

      const response = await fetch(RESEARCH_API, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(apiBody),
      });

      if (!response.ok) {
        const errorEvent = `data: ${JSON.stringify({ type: 'error', message: `Research API error: ${response.status}` })}\n\n`;
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
      console.error('[query-research-stream] Error:', err);
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
