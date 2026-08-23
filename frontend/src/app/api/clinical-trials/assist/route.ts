import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = (process.env.BACKEND_URL || "http://localhost:8000") + "/v1/clinical-trials/assist";

export async function POST(request: NextRequest) {
  const auth = request.headers.get("Authorization");
  if (!auth?.startsWith("Bearer ")) {
    return Response.json({ detail: "Unauthorized" }, { status: 401 });
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ detail: "Invalid JSON" }, { status: 400 });
  }
  const res = await fetch(BACKEND, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: auth,
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({}));
  return Response.json(data, { status: res.status });
}
