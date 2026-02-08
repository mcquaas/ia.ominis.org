import { NextRequest, NextResponse } from 'next/server';

// Ominis Agent backend - Non-streaming query (can also use MEXICO_API_URL for legacy)
const MEXICO_API = process.env.MEXICO_API_URL || (process.env.BACKEND_URL || 'http://localhost:8000') + '/v1/query';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    
    const response = await fetch(MEXICO_API, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      throw new Error(`Mexico API error: ${response.status}`);
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Mexico API error:', error);
    return NextResponse.json(
      { error: 'Error connecting to Mexico server', answer: 'Lo siento, hubo un error. Por favor intenta de nuevo.' },
      { status: 500 }
    );
  }
}

export async function OPTIONS() {
  return NextResponse.json({}, { status: 200 });
}
