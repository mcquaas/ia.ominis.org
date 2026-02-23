import { NextRequest, NextResponse } from 'next/server';

// Ominis Agent backend - Non-streaming query endpoint
const GPU_API = (process.env.BACKEND_URL || 'http://localhost:8000') + '/v1/query';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    
    // Transform request for backend API
    const apiBody = {
      question: body.question,
      history: body.history,
      image: body.images && body.images.length > 0 ? body.images[0] : undefined,
      rag_search: body.rag_search !== false, // Default to true
      web_search: body.web_search !== false, // Default to true
      pubmed_search: body.pubmed_search !== false, // Default to true
      openscholar_search: body.openscholar_search === true, // Default off
      num_sources: body.num_sources || 5,
    };
    
    const response = await fetch(GPU_API, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(apiBody),
    });

    if (!response.ok) {
      throw new Error(`GPU API error: ${response.status}`);
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('GPU API error:', error);
    return NextResponse.json(
      { error: 'Error connecting to GPU server', answer: 'Lo siento, hubo un error. Por favor intenta de nuevo.' },
      { status: 500 }
    );
  }
}

export async function OPTIONS() {
  return NextResponse.json({}, { status: 200 });
}
