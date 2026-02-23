/**
 * LiveAvatar session — create HeyGen LiveAvatar session and return join URL.
 * mode=heygen: HeyGen FULL (default LLM). mode=pipecat: Ominis BioMistral.
 */
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(req: Request) {
  try {
    let body: { mode?: string } = {};
    try {
      body = (await req.json()) as { mode?: string };
    } catch {
      // No body or invalid JSON
    }
    const res = await fetch(`${BACKEND_URL}/v1/liveavatar/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      return Response.json(
        { error: data.detail || data.message || "Session creation failed" },
        { status: res.status }
      );
    }
    return Response.json(data);
  } catch (err) {
    console.error("[liveavatar/session]", err);
    return Response.json(
      { error: "Could not reach backend" },
      { status: 502 }
    );
  }
}
