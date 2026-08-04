import { NextResponse } from 'next/server';

/**
 * API proxy to CrewAI Flask agent service.
 * Forwards to http://localhost:5012/chat (with fallback to http://localhost:5000/chat)
 */
export async function POST(req: Request) {
  try {
    const body = await req.json();
    const port = process.env.CREWAI_PORT || '5012';

    let res;
    try {
      res = await fetch(`http://localhost:${port}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } catch (e) {
      // If the primary port failed, try 5000 as a fallback
      if (port !== '5000') {
        res = await fetch('http://localhost:5000/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
      } else {
        throw e;
      }
    }

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    return NextResponse.json(
      { error: 'Failed to connect to CrewAI agent service' },
      { status: 502 }
    );
  }
}
