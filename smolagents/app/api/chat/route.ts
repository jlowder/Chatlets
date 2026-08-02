import { NextResponse } from 'next/server';

export async function POST(request: Request) {
  const t0 = Date.now();
  console.log(`[smolagents proxy] POST /api/chat started at ${new Date().toISOString()}`);
  
  try {
    const agentUrl = 'http://localhost:5010/chat';
    const body = JSON.stringify(await request.json());
    console.log(`[smolagents proxy] Body parsed in ${Date.now() - t0}ms`);
    
    const fetchStart = Date.now();
    const res = await fetch(agentUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) + '' },
      body,
      signal: AbortSignal.timeout(300000), // 5 min
      // Force HTTP/1.1 to avoid keep-alive/connection pooling issues with Flask
      keepAlive: false,
    });
    const fetchElapsed = Date.now() - fetchStart;
    console.log(`[smolagents proxy] Agent responded in ${fetchElapsed}ms with status ${res.status}`);
    
    const jsonStart = Date.now();
    const data = await res.json();
    const jsonElapsed = Date.now() - jsonStart;
    console.log(`[smolagents proxy] JSON parsed in ${jsonElapsed}ms`);
    
    const totalElapsed = Date.now() - t0;
    if (!res.ok) {
      console.log(`[smolagents proxy] Error response:`, data);
      return NextResponse.json({ error: data.error || 'Backend error' }, { status: res.status });
    }
    console.log(`[smolagents proxy] Success in ${totalElapsed}ms (body:${fetchElapsed}ms json:${jsonElapsed}ms)`);
    return NextResponse.json(data);
  } catch (err: unknown) {
    const elapsed = Date.now() - t0;
    const msg = err instanceof Error ? err.message : 'Unknown error';
    console.log(`[smolagents proxy] Failed after ${elapsed}ms: ${msg}`);
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
