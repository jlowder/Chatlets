import { NextResponse } from 'next/server';

/**
 * API Route that proxies to the Python Agno Agent Service.
 * The agno agent logic runs in a separate Flask service on port 8081.
 * 
 * Usage:
 *   1. Start agent service: python agent_service.py  (or npm run agent)
 *   2. Start Next.js: npm run dev
 */

const AGENT_SERVICE_URL = process.env.AGENT_SERVICE_URL || 'http://localhost:8081';

export async function POST(request: Request) {
  try {
    const { prompt } = await request.json();
    if (!prompt) {
      return NextResponse.json({ error: 'Missing prompt' }, { status: 400 });
    }

    const res = await fetch(`${AGENT_SERVICE_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt }),
    });

    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { error: data.error ?? 'Agent service error', text: '', toolOutputs: [] },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (e: any) {
    console.error('API route error:', e);
    return NextResponse.json(
      { error: e.message ?? 'Internal error', text: '', toolOutputs: [] },
      { status: 500 }
    );
  }
}
