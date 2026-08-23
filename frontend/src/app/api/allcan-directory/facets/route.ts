import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const DEFAULT_BASE = "https://api.allcan.mx";

function strapiBase(): string {
  return (process.env.ALLCAN_STRAPI_URL || DEFAULT_BASE).replace(/\/$/, "");
}

function strapiToken(): string | undefined {
  const t = process.env.ALLCAN_STRAPI_API_TOKEN?.trim();
  return t || undefined;
}

/**
 * GET /api/allcan-directory/facets — distinct type / state / specialty for filter dropdowns (JWT required).
 */
export async function GET(request: NextRequest) {
  const auth = request.headers.get("Authorization");
  if (!auth || !auth.startsWith("Bearer ")) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  const token = strapiToken();
  if (!token) {
    return Response.json(
      { error: "All.Can Strapi token not configured (ALLCAN_STRAPI_API_TOKEN)." },
      { status: 503 },
    );
  }

  const base = strapiBase();
  const qs = new URLSearchParams();
  qs.append("pagination[pageSize]", "200");
  qs.append("pagination[page]", "1");
  qs.append("fields[0]", "type");
  qs.append("fields[1]", "state");
  qs.append("fields[2]", "specialty");

  const res = await fetch(`${base}/api/organizations?${qs.toString()}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  const raw = await res.json().catch(() => ({}));
  if (!res.ok) {
    return Response.json(
      typeof raw === "object" && raw !== null ? raw : { error: "Strapi error" },
      { status: res.status },
    );
  }

  const rows = Array.isArray((raw as { data?: unknown[] }).data)
    ? ((raw as { data: { type?: string; state?: string; specialty?: string }[] }).data)
    : [];

  const types = new Set<string>();
  const states = new Set<string>();
  const specialties = new Set<string>();
  for (const r of rows) {
    if (r.type?.trim()) types.add(r.type.trim());
    if (r.state?.trim()) states.add(r.state.trim());
    if (r.specialty?.trim()) specialties.add(r.specialty.trim());
  }

  return Response.json({
    types: [...types].sort((a, b) => a.localeCompare(b, "es")),
    states: [...states].sort((a, b) => a.localeCompare(b, "es")),
    specialties: [...specialties].sort((a, b) => a.localeCompare(b, "es")),
    total: (raw as { meta?: { pagination?: { total?: number } } }).meta?.pagination?.total ?? rows.length,
  });
}
