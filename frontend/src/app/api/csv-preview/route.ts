import { NextRequest, NextResponse } from "next/server";

const MAX_ROWS = 26;
const MAX_BYTES = 2_500_000;

function parseCsvLine(line: string): string[] {
  const result: string[] = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (inQuotes) {
      if (c === '"') {
        if (line[i + 1] === '"') {
          cur += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        cur += c;
      }
    } else if (c === '"') {
      inQuotes = true;
    } else if (c === ",") {
      result.push(cur);
      cur = "";
    } else {
      cur += c;
    }
  }
  result.push(cur);
  return result;
}

function isAllowedUrl(urlStr: string): boolean {
  try {
    const u = new URL(urlStr);
    if (u.protocol !== "https:" && u.protocol !== "http:") return false;
    const h = u.hostname.toLowerCase();
    if (h === "localhost" || h === "127.0.0.1") return true;
    if (h.endsWith("ominis.org")) return true;
    if (h.endsWith(".gob.mx")) return true;
    return false;
  } catch {
    return false;
  }
}

function safeFilenameFromUrl(urlStr: string): string {
  try {
    const u = new URL(urlStr);
    const seg = u.pathname.split("/").filter(Boolean).pop() || "datos.csv";
    return seg.replace(/[^\w.\-]/g, "_").slice(0, 120) || "datos.csv";
  } catch {
    return "datos.csv";
  }
}

export async function GET(request: NextRequest) {
  const url = request.nextUrl.searchParams.get("url");
  const download = request.nextUrl.searchParams.get("download") === "1";
  if (!url || !isAllowedUrl(url)) {
    return NextResponse.json({ error: "URL no permitida o inválida" }, { status: 400 });
  }

  try {
    const res = await fetch(url, {
      headers: { "User-Agent": "Ominis-CSV-Preview/1.0" },
      redirect: "follow",
      signal: AbortSignal.timeout(60_000),
    });
    if (!res.ok) {
      return NextResponse.json({ error: `No se pudo descargar (${res.status})` }, { status: 502 });
    }

    if (download) {
      const buf = await res.arrayBuffer();
      const ct = res.headers.get("content-type") || "text/csv; charset=utf-8";
      const name = safeFilenameFromUrl(url);
      return new NextResponse(buf, {
        headers: {
          "Content-Type": ct,
          "Content-Disposition": `attachment; filename="${name}"`,
        },
      });
    }

    const buf = await res.arrayBuffer();
    const slice = buf.byteLength > MAX_BYTES ? buf.slice(0, MAX_BYTES) : buf;
    const text = new TextDecoder("utf-8", { fatal: false }).decode(slice);
    const lines = text.split(/\r?\n/).filter((l) => l.length > 0);
    const rows = lines.slice(0, MAX_ROWS).map(parseCsvLine);
    const truncated = lines.length > MAX_ROWS || buf.byteLength > MAX_BYTES;
    return NextResponse.json({
      rows,
      truncated,
      rawText: text,
    });
  } catch (e) {
    console.error("csv-preview", e);
    return NextResponse.json({ error: "Error al obtener el CSV" }, { status: 500 });
  }
}
