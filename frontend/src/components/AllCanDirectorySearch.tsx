"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { getToken } from "@/services/auth";

const AllCanLeafletMap = dynamic(() => import("./AllCanLeafletMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[min(360px,40vh)] w-full items-center justify-center rounded-lg border border-white/10 bg-[#0a1628]/60 text-sm text-gray-500">
      Cargando mapa…
    </div>
  ),
});

type Organization = {
  id: number;
  name: string;
  address?: string | null;
  description?: string | null;
  email?: string | null;
  phone?: string | null;
  url?: string | null;
  latitude?: string | null;
  longitude?: string | null;
  state?: string | null;
  city?: string | null;
  logo_url?: string | null;
  type?: string | null;
  specialty?: string | null;
};

type StrapiListResponse = {
  data?: Organization[];
  meta?: {
    pagination?: { page?: number; pageSize?: number; pageCount?: number; total?: number };
  };
  error?: { message?: string };
};

type FacetsResponse = {
  types: string[];
  states: string[];
  specialties: string[];
  total?: number;
  error?: string;
};

function mapsUrl(lat: string, lng: string): string {
  return `https://www.google.com/maps?q=${encodeURIComponent(`${lat},${lng}`)}`;
}

function LogoThumb({ url }: { url: string | null | undefined }) {
  const [broken, setBroken] = useState(false);
  useEffect(() => {
    setBroken(false);
  }, [url]);

  if (!url || broken) {
    return (
      <div className="w-full h-full flex items-center justify-center text-gray-500 text-xs bg-white/[0.03]">
        —
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={url}
      alt=""
      className="w-full h-full object-contain p-1"
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setBroken(true)}
    />
  );
}

export default function AllCanDirectorySearch({ layout = "dialog" }: { layout?: "dialog" | "inline" }) {
  const isInline = layout === "inline";
  const [open, setOpen] = useState(isInline);
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [state, setState] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [city, setCity] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [facetsLoading, setFacetsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<StrapiListResponse | null>(null);
  const [facets, setFacets] = useState<FacetsResponse | null>(null);
  const [mapScope, setMapScope] = useState<"page" | "all">("page");
  const [mapAllOrgs, setMapAllOrgs] = useState<Organization[] | null>(null);
  const [mapAllLoading, setMapAllLoading] = useState(false);
  const [focusMapId, setFocusMapId] = useState<number | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const qRef = useRef<HTMLInputElement>(null);

  const searchParamsForRequest = useCallback(
    (pageNum: number, pageSize: number) => {
      const params = new URLSearchParams();
      if (q.trim()) params.set("q", q.trim());
      if (type.trim()) params.set("type", type.trim());
      if (state.trim()) params.set("state", state.trim());
      if (specialty.trim()) params.set("specialty", specialty.trim());
      if (city.trim()) params.set("city", city.trim());
      params.set("page", String(pageNum));
      params.set("pageSize", String(pageSize));
      params.set("semantic", "true");
      return params;
    },
    [q, type, state, specialty, city],
  );

  useEffect(() => {
    if (!open || isInline) return;
    const t = window.setTimeout(() => qRef.current?.focus(), 50);
    return () => window.clearTimeout(t);
  }, [open, isInline]);

  useEffect(() => {
    if (!open || isInline) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, isInline]);

  useEffect(() => {
    if (!open || isInline) return;
    function onDoc(e: MouseEvent) {
      const t = e.target as Node;
      if (panelRef.current && !panelRef.current.contains(t)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open, isInline]);

  useEffect(() => {
    if (!open) return;
    const jwt = getToken();
    if (!jwt) return;
    setFacetsLoading(true);
    fetch("/api/allcan-directory/facets", {
      headers: { Authorization: `Bearer ${jwt}` },
      cache: "no-store",
    })
      .then(async (res) => {
        const j = (await res.json()) as FacetsResponse;
        if (!res.ok) {
          setFacets(null);
          return;
        }
        setFacets(j);
      })
      .catch(() => setFacets(null))
      .finally(() => setFacetsLoading(false));
  }, [open]);

  const runSearch = async (nextPage = 1) => {
    const jwt = getToken();
    if (!jwt) {
      setError("Sesión requerida.");
      return;
    }
    setLoading(true);
    setError(null);
    setData(null);
    setMapScope("page");
    setMapAllOrgs(null);
    setFocusMapId(null);
    try {
      const params = searchParamsForRequest(nextPage, 24);
      const res = await fetch(`/api/allcan-directory/search?${params.toString()}`, {
        headers: { Authorization: `Bearer ${jwt}` },
        cache: "no-store",
      });
      const json = (await res.json()) as StrapiListResponse;
      if (!res.ok) {
        const err = (json as { error?: string | { message?: string } }).error;
        const msg =
          (typeof err === "string" ? err : err?.message) ||
          (json as { message?: string }).message ||
          `Error ${res.status}`;
        setError(typeof msg === "string" ? msg : "Error al consultar All.Can.");
        return;
      }
      setData(json);
      setPage(nextPage);
    } catch {
      setError("Error de red. Intenta de nuevo.");
    } finally {
      setLoading(false);
    }
  };

  const loadAllOrganizationsForMap = async () => {
    const jwt = getToken();
    if (!jwt) {
      setError("Sesión requerida.");
      return;
    }
    setMapAllLoading(true);
    setError(null);
    try {
      const firstParams = searchParamsForRequest(1, 200);
      const res = await fetch(`/api/allcan-directory/search?${firstParams.toString()}`, {
        headers: { Authorization: `Bearer ${jwt}` },
        cache: "no-store",
      });
      const json = (await res.json()) as StrapiListResponse;
      if (!res.ok) {
        const err = (json as { error?: string | { message?: string } }).error;
        const msg =
          (typeof err === "string" ? err : err?.message) ||
          (json as { message?: string }).message ||
          `Error ${res.status}`;
        setError(typeof msg === "string" ? msg : "Error al consultar All.Can.");
        return;
      }
      let rows = [...(json.data || [])];
      const total = json.meta?.pagination?.total ?? rows.length;
      let page = 2;
      while (rows.length < total && page <= 30) {
        const p = searchParamsForRequest(page, 200);
        const r = await fetch(`/api/allcan-directory/search?${p.toString()}`, {
          headers: { Authorization: `Bearer ${jwt}` },
          cache: "no-store",
        });
        const j = (await r.json()) as StrapiListResponse;
        if (!r.ok) break;
        const chunk = j.data || [];
        rows = rows.concat(chunk);
        if (chunk.length < 200) break;
        page += 1;
      }
      setMapAllOrgs(rows);
      setMapScope("all");
      setFocusMapId(null);
    } catch {
      setError("Error de red al cargar el mapa completo.");
    } finally {
      setMapAllLoading(false);
    }
  };

  const mapOrganizations = useMemo(() => {
    if (mapScope === "all" && mapAllOrgs) return mapAllOrgs;
    return data?.data ?? [];
  }, [mapScope, mapAllOrgs, data?.data]);

  const mapPointsCount = useMemo(() => {
    return mapOrganizations.filter((o) => {
      const la = o.latitude?.trim();
      const ln = o.longitude?.trim();
      if (!la || !ln) return false;
      const a = Number(la);
      const b = Number(ln);
      return !Number.isNaN(a) && !Number.isNaN(b);
    }).length;
  }, [mapOrganizations]);

  const pagination = data?.meta?.pagination;
  const total = pagination?.total ?? 0;
  const pageCount = pagination?.pageCount ?? 1;

  const panelClass =
    "w-full max-h-[94vh] sm:max-h-[90vh] sm:max-w-4xl lg:max-w-5xl flex flex-col rounded-t-2xl sm:rounded-2xl border border-white/15 bg-[#0f1d32]/98 shadow-2xl shadow-black/50 overflow-hidden";

  const panel = (
            <div
              ref={panelRef}
              role="dialog"
              aria-modal={!isInline}
              aria-labelledby={titleId}
              className={isInline ? `${panelClass} max-h-[min(85vh,800px)]` : panelClass}
            >
              <div className="flex items-start justify-between gap-3 px-4 py-3 border-b border-white/10">
                <div>
                  <h2 id={titleId} className="text-base font-semibold text-white">
                    Directorio All.Can México
                  </h2>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Organizaciones del mapa interactivo (
                    <a
                      href="https://www.allcan.mx/mapa-interactivo-all-can/"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-orange-300 hover:underline"
                    >
                      allcan.mx
                    </a>
                    ). Datos vía{" "}
                    <a
                      href="https://api.allcan.mx"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-orange-300 hover:underline"
                    >
                      api.allcan.mx
                    </a>{" "}
                    (Strapi).
                  </p>
                </div>
                {!isInline && (
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="shrink-0 p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/10"
                  aria-label="Cerrar"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
                )}
              </div>

              <form
                className="px-4 py-3 border-b border-white/10 space-y-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void runSearch(1);
                }}
              >
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                  <input
                    ref={qRef}
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    placeholder="Nombre, tipo, especialidad, dirección…"
                    className="rounded-lg bg-[#0a1628] border border-white/15 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-orange-500/40"
                  />
                  <input
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                    placeholder="Ciudad / alcaldía (contiene)"
                    className="rounded-lg bg-[#0a1628] border border-white/15 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-orange-500/40"
                  />
                  <select
                    value={type}
                    onChange={(e) => setType(e.target.value)}
                    disabled={facetsLoading}
                    className="rounded-lg bg-[#0a1628] border border-white/15 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-orange-500/40"
                    aria-label="Tipo de organización"
                  >
                    <option value="">Todos los tipos</option>
                    {(facets?.types || []).map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                  <select
                    value={state}
                    onChange={(e) => setState(e.target.value)}
                    disabled={facetsLoading}
                    className="rounded-lg bg-[#0a1628] border border-white/15 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-orange-500/40"
                    aria-label="Estado"
                  >
                    <option value="">Todos los estados</option>
                    {(facets?.states || []).map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                  <select
                    value={specialty}
                    onChange={(e) => setSpecialty(e.target.value)}
                    disabled={facetsLoading}
                    className="rounded-lg bg-[#0a1628] border border-white/15 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-orange-500/40"
                    aria-label="Especialidad / enfoque"
                  >
                    <option value="">Todas las especialidades</option>
                    {(facets?.specialties || []).map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>
                <p className="text-[10px] text-gray-500 -mt-1">
                  {facetsLoading
                    ? "Cargando filtros…"
                    : facets != null
                      ? `${facets.total ?? "—"} organizaciones en el índice.`
                      : ""}
                </p>
                <button
                  type="submit"
                  disabled={loading}
                  className="rounded-lg bg-orange-600/80 hover:bg-orange-500 text-white text-sm font-medium px-4 py-2 disabled:opacity-50"
                >
                  {loading ? "Buscando…" : "Buscar"}
                </button>
              </form>

              <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3 space-y-3">
                {error && (
                  <p className="text-sm text-red-300" role="alert">
                    {error}
                  </p>
                )}
                {data?.data && (
                  <>
                    <p className="text-xs text-gray-500">
                      {total} resultado(s)
                      {pagination ? ` · Página ${pagination.page ?? page} de ${pageCount}` : ""}.
                    </p>

                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs text-gray-500">
                          Mapa:{" "}
                          {mapScope === "all"
                            ? `todos los resultados de la búsqueda (${mapOrganizations.length} org.)`
                            : `esta página (${data.data.length} org.)`}
                          {mapPointsCount > 0 && (
                            <span className="text-orange-200/80"> · {mapPointsCount} con coordenadas</span>
                          )}
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          disabled={mapAllLoading || !data}
                          onClick={() => {
                            setMapScope("page");
                            setMapAllOrgs(null);
                            setFocusMapId(null);
                          }}
                          className="text-xs rounded-lg border border-white/20 px-3 py-1.5 text-gray-200 hover:bg-white/10 disabled:opacity-40"
                        >
                          Mapa: solo esta página
                        </button>
                        <button
                          type="button"
                          disabled={mapAllLoading || loading}
                          onClick={() => void loadAllOrganizationsForMap()}
                          className="text-xs rounded-lg bg-orange-600/50 hover:bg-orange-500/80 text-white px-3 py-1.5 disabled:opacity-40"
                        >
                          {mapAllLoading ? "Cargando puntos…" : "Mapa: todos los resultados"}
                        </button>
                      </div>
                      {mapScope === "all" && (
                        <p className="text-[10px] text-gray-500">
                          La lista sigue paginada; el mapa muestra todas las organizaciones que coinciden con los filtros
                          (hasta 200 por petición, varias peticiones si hace falta).
                        </p>
                      )}
                      <AllCanLeafletMap
                        key={`${mapScope}-${mapOrganizations.length}-${mapOrganizations[0]?.id ?? 0}`}
                        organizations={mapOrganizations}
                        focusId={focusMapId}
                      />
                    </div>

                    {data.data.map((o) => {
                      const lat = o.latitude?.trim();
                      const lng = o.longitude?.trim();
                      const hasCoords =
                        lat && lng && !Number.isNaN(Number(lat)) && !Number.isNaN(Number(lng));
                      return (
                        <article
                          key={o.id}
                          role="button"
                          tabIndex={0}
                          onClick={() => setFocusMapId(o.id)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              setFocusMapId(o.id);
                            }
                          }}
                          className="rounded-xl border border-white/10 bg-white/[0.04] overflow-hidden cursor-pointer hover:border-orange-500/25 transition-colors text-left"
                        >
                          <div className="flex gap-3 p-3">
                            <div className="shrink-0 w-16 h-16 sm:w-20 sm:h-20 rounded-lg bg-white/5 overflow-hidden border border-white/10">
                              <LogoThumb url={o.logo_url} />
                            </div>
                            <div className="min-w-0 flex-1">
                              <h3 className="text-sm font-semibold text-white leading-snug">{o.name}</h3>
                              <p className="text-xs text-orange-200/90 mt-0.5">
                                {[o.type, o.specialty].filter(Boolean).join(" · ")}
                              </p>
                              {(o.city || o.state) && (
                                <p className="text-xs text-gray-400 mt-1">
                                  {[o.city, o.state].filter(Boolean).join(", ")}
                                </p>
                              )}
                            </div>
                          </div>
                          {o.address && (
                            <div className="px-3 pb-2 text-xs text-gray-400 border-t border-white/5 pt-2">
                              <span className="text-gray-500">Dirección: </span>
                              {o.address}
                            </div>
                          )}
                          {o.description && (
                            <p className="px-3 pb-2 text-xs text-gray-400 leading-snug">{o.description}</p>
                          )}
                          <div className="flex flex-wrap gap-2 px-3 pb-3 pt-1 border-t border-white/5">
                            {o.url && (
                              <a
                                href={o.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-xs rounded-lg bg-orange-600/70 hover:bg-orange-500 text-white px-3 py-1.5"
                                onClick={(e) => e.stopPropagation()}
                              >
                                Sitio web
                              </a>
                            )}
                            {hasCoords && (
                              <a
                                href={mapsUrl(lat!, lng!)}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-xs rounded-lg border border-white/20 text-gray-200 px-3 py-1.5 hover:bg-white/10"
                                onClick={(e) => e.stopPropagation()}
                              >
                                Mapa
                              </a>
                            )}
                            {o.phone && (
                              <a
                                href={`tel:${String(o.phone).replace(/[^\d+]/g, "")}`}
                                className="text-xs rounded-lg border border-white/20 text-gray-200 px-3 py-1.5 hover:bg-white/10"
                                onClick={(e) => e.stopPropagation()}
                              >
                                Llamar
                              </a>
                            )}
                            {o.email && (
                              <a
                                href={`mailto:${o.email}`}
                                className="text-xs rounded-lg border border-white/20 text-gray-200 px-3 py-1.5 hover:bg-white/10"
                                onClick={(e) => e.stopPropagation()}
                              >
                                Correo
                              </a>
                            )}
                          </div>
                        </article>
                      );
                    })}
                    {pageCount > 1 && (
                      <div className="flex flex-wrap gap-2 items-center pt-1">
                        <button
                          type="button"
                          disabled={loading || page <= 1}
                          onClick={() => void runSearch(page - 1)}
                          className="text-xs rounded-lg bg-white/10 px-3 py-1.5 text-white disabled:opacity-40"
                        >
                          Anterior
                        </button>
                        <button
                          type="button"
                          disabled={loading || page >= pageCount}
                          onClick={() => void runSearch(page + 1)}
                          className="text-xs rounded-lg bg-white/10 px-3 py-1.5 text-white disabled:opacity-40"
                        >
                          Siguiente
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>

              <div className="px-4 py-2 border-t border-white/10 bg-black/20">
                <p className="text-[10px] text-gray-500 leading-snug">
                  All.Can México — FUNSALUD. Verifica datos de contacto en el sitio de cada organización antes de
                  usar información sensible.
                </p>
              </div>
            </div>
  );

  if (isInline) {
    return <div className="w-full">{panel}</div>;
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/5 px-2.5 py-1.5 text-xs text-gray-200 hover:border-orange-400/30 hover:bg-white/10 hover:text-white transition-colors md:px-3"
        title="Directorio interactivo All.Can México (Strapi)"
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        <svg className="w-4 h-4 text-orange-300 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"
          />
        </svg>
        <span className="hidden sm:inline max-w-[10rem] truncate">All.Can MX</span>
      </button>

      {open &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            className="fixed inset-0 z-[2147483646] flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/60 backdrop-blur-sm"
            role="presentation"
          >
            {panel}
          </div>,
          document.body,
        )}
    </>
  );
}
