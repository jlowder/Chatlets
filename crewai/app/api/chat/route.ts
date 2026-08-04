import { NextResponse } from 'next/server';

/**
 * API proxy to CrewAI Flask agent service.
 * Forwards to http://localhost:5012/chat (with fallback to http://localhost:5000/chat)
 */
export async function POST(req: Request) {
  try {
    const body = await req.json();
    const port = process.env.CREWAI_PORT || '5012';
    const url = `http://localhost:${port}/chat`;

    console.log(`[crewai proxy] Received chat request. Forwarding to primary agent service at: ${url}`);

    let res;
    try {
      res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } catch (e: any) {
      console.warn(`[crewai proxy] Failed to connect to primary agent service on port ${port}: ${e.message}`);

      // If the primary port failed, try 5000 as a fallback
      if (port !== '5000') {
        const fallbackUrl = 'http://localhost:5000/chat';
        console.log(`[crewai proxy] Attempting fallback to agent service at: ${fallbackUrl}`);
        res = await fetch(fallbackUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
      } else {
        throw e;
      }
    }

    console.log(`[crewai proxy] Successfully connected to agent service. Status: ${res.status}`);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (e: any) {
    console.error(`[crewai proxy] Connection error: Failed to connect to CrewAI Flask agent service. Details: ${e.message}`);
    return NextResponse.json(
      { error: `Failed to connect to CrewAI agent service: ${e.message}` },
      { status: 502 }
    );
  }
}
