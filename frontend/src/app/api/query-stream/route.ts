import { NextRequest } from 'next/server';

// Force dynamic runtime for streaming
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 900; // 15 min — Research 2.1 deep multi-round can take 10-15 min

// Ominis Agent backend - Streaming endpoint
const GPU_API = (process.env.BACKEND_URL || 'http://localhost:8000') + '/v1/query-stream';

export async function POST(request: NextRequest) {
  const encoder = new TextEncoder();
  
  // Create a TransformStream to handle the streaming
  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();
  
  // Start the async operation
  (async () => {
    try {
      const body = await request.json();

      // Transform request for backend API (orchestrator uses research_mode to route to Research 128K)
      const apiBody: Record<string, unknown> = {
        question: body.question,
        history: body.history,
        image: body.images && body.images.length > 0 ? body.images[0] : undefined,
        model: body.model || undefined,
        research_mode: body.research_mode === true,
        rag_search: body.rag_search !== false,
        web_search: body.web_search !== false,
        pubmed_search: body.pubmed_search !== false,
        openscholar_search: body.openscholar_search === true,
        file_context: body.file_context || undefined,
      };
      if (body.research_mode) {
        apiBody.research_2_1 = body.research_2_1 === true;
        if (Array.isArray(body.excluded_sources)) apiBody.excluded_sources = body.excluded_sources;
      }

      console.log('[query-stream] Request:', typeof apiBody.question === 'string' ? apiBody.question.slice(0, 50) : '', 'model:', apiBody.model || 'default');

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 130_000); // 130s, slightly above backend 120s

      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      const auth = request.headers.get('Authorization');
      if (auth) headers['Authorization'] = auth;

      const response = await fetch(GPU_API, {
        method: 'POST',
        headers,
        body: JSON.stringify(apiBody),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!response.ok) {
        let message = `GPU API error: ${response.status}`;
        let reason: string | undefined;
        try {
          const errBody = await response.json();
          if (errBody?.detail?.code === 'model_not_allowed' && errBody?.detail?.reason) {
            reason = errBody.detail.reason;
            message = reason === 'login_required'
              ? 'Inicia sesión para usar este modelo.'
              : reason === 'request_superadmin'
                ? 'Este modelo requiere autorización del SuperAdmin. Solicita acceso.'
                : message;
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

      // Stream chunks as they arrive
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        const chunk = decoder.decode(value, { stream: true });
        await writer.write(encoder.encode(chunk));
      }

      await writer.close();
    } catch (error: unknown) {
      const err = error as Error & { code?: string; name?: string };
      console.error('[query-stream] Error:', err);
      const reason = err?.name === 'AbortError'
        ? 'El servidor tardó demasiado en responder. Intenta de nuevo.'
        : err?.code === 'ECONNREFUSED'
          ? 'Backend no disponible (ECONNREFUSED)'
          : err?.code === 'ETIMEDOUT'
            ? 'Timeout al conectar con el backend'
            : err?.message || 'Connection error';
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
      'X-Accel-Buffering': 'no', // Disable nginx buffering
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
