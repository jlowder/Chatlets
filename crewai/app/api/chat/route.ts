import { NextResponse } from 'next/server';

/**
 * API proxy to CrewAI Flask agent service.
 * Forwards to http://localhost:5000/chat
 */
export async function POST(req: Request) {
  try {
    const body = await req.json();
    const res = await fetch('http://localhost:5000/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    return NextResponse.json(
      { error: 'Failed to connect to CrewAI agent service' },
      { status: 502 }
    );
  }
}
