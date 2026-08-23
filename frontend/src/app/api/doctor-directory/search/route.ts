import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND =
  process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * GET /api/doctor-directory/search — proxy to Haystack /v1/doctor-directory/search (JWT required).
 */
export async function GET(request: NextRequest) {
  const auth = request.headers.get("Authorization");
  if (!auth || !auth.startsWith("Bearer ")) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  const q = request.nextUrl.searchParams.toString();
  const url = `${BACKEND}/v1/doctor-directory/search${q ? `?${q}` : ""}`;
  const res = await fetch(url, {
    headers: { Authorization: auth },
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({}));
  return Response.json(data, { status: res.status });
}
