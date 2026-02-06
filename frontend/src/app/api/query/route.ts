import { NextRequest, NextResponse } from 'next/server';

// Mexico RAG API - 100% data in Mexican territory
const MEXICO_API = process.env.MEXICO_API_URL || 'https://api.ominis.org/query';

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
