import { NextRequest } from 'next/server';

// Force dynamic runtime for streaming
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 120; // 2 minutes max

// GPU RAG API - Streaming endpoint
const GPU_API = process.env.GPU_API_URL || 'http://44.215.64.245:8080/query-stream';

export async function POST(request: NextRequest) {
  const encoder = new TextEncoder();
  
  // Create a TransformStream to handle the streaming
  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();
  
  // Start the async operation
  (async () => {
    try {
      const body = await request.json();

      // Transform request for backend API
      const apiBody = {
        question: body.question,
        history: body.history,
        image: body.images && body.images.length > 0 ? body.images[0] : undefined,
        rag_search: body.rag_search !== false,
        web_search: body.web_search !== false,
        pubmed_search: body.pubmed_search !== false,
      };

      console.log('[query-stream] Request:', apiBody.question?.slice(0, 50));

      const response = await fetch(GPU_API, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(apiBody),
      });

      if (!response.ok) {
        const errorEvent = `data: ${JSON.stringify({ type: 'error', message: `GPU API error: ${response.status}` })}\n\n`;
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
    } catch (error) {
      console.error('[query-stream] Error:', error);
      const errorEvent = `data: ${JSON.stringify({ type: 'error', message: 'Connection error' })}\n\n`;
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
