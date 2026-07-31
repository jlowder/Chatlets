import { NextResponse } from 'next/server';

/**
 * API proxy to Agno Flask agent service.
 * Forwards to http://localhost:8081/chat (Flask endpoint).
 *
 * Usage:
 *   1. Start agent service: npm run agent  (or npm run dev:all)
 *   2. Start proxy:        npm run dev
 */
export async function POST(req: Request) {
  try {
    const body = await req.json();
    const res = await fetch('http://localhost:8081/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { error: 'Failed to connect to Agno agent service' },
      { status: 502 }
    );
  }
}
