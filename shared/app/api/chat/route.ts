import { NextRequest, NextResponse } from 'next/server';

// Backend URL map (mirrors backends.ts)
const BACKEND_MAP: Record<string, string> = {
  'vercel-ai': 'http://localhost:4000/api/chat',
  agno: 'http://localhost:3001/api/chat',
  crewai: 'http://localhost:5000/chat',
  langchain: 'http://localhost:5001/api/chat',
  langgraph: 'http://localhost:5002/api/chat',
  liw: 'http://localhost:5003/api/chat',
  maf: 'http://localhost:5005/api/chat',
  mastra: 'http://localhost:5007/api/chat',
  pydantic: 'http://localhost:5009/api/chat',
  smolagents: 'http://localhost:5011/api/chat',
};

export async function POST(request: NextRequest) {
  const backend = request.headers.get('x-chatlet-backend') || process.env.CHATLET_BACKEND || 'vercel-ai';
  const backendUrl = BACKEND_MAP[backend];

  if (!backendUrl) {
    return NextResponse.json({ error: `Unknown backend: ${backend}` }, { status: 502 });
  }

  try {
    const body = await request.text();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 300_000); // 5 min

    const res = await fetch(backendUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      signal: controller.signal,
    });

    clearTimeout(timeout);

    const data = await res.text();

    return new NextResponse(data, {
      status: res.status,
      headers: { 'Content-Type': res.headers.get('Content-Type') || 'application/json' },
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Unknown error';
    console.error(`[shared proxy] Failed: ${msg}`);
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
