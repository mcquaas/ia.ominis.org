"use client";

import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { getToken } from "@/services/auth";

type SourceAppearance = {
  source_site: string;
  profile_slug?: string;
  profile_url: string;
  last_scraped_at?: string | null;
  scrape_run_id?: number | null;
  rating_value?: number | null;
  rating_count?: number | null;
};

type ExternalReview = {
  platform?: string;
  rating?: number;
  rating_value?: number;
  max_rating?: number;
  review_count?: number;
  count?: number;
};

type DoctorHit = {
  id: number;
  source_site: string;
  profile_url: string;
  source_appearances?: SourceAppearance[];
  display_name: string;
  specialty_label?: string | null;
  specialties_json?: string[] | null;
  description?: string | null;
  image_url?: string | null;
  street_address?: string | null;
  locality?: string | null;
  region?: string | null;
  postal_code?: string | null;
  services_json?: string[] | null;
  phones_json?: string[] | null;
  external_reviews_json?: ExternalReview[] | null;
  rating_value?: number | null;
  rating_count?: number | null;
  rating_best?: number | null;
  last_scraped_at?: string;
};

type SearchResponse = {
  total?: number;
  results?: DoctorHit[];
  disclaimer?: string;
  detail?: string;
};

function locationLine(d: DoctorHit): string {
  const parts = [d.locality, d.region].filter(Boolean);
  return parts.join(", ");
}

/** Source scale (e.g. DoctorAnytime uses /10); UI always shows 5 stars. */
function ratingScaleMax(d: DoctorHit): number {
  const b = d.rating_best;
  if (b != null && b > 5) return b;
  return 5;
}

function filledStarsOutOfFive(value: number, scaleMax: number): number {
  const sm = scaleMax > 0 ? scaleMax : 5;
  return Math.round(Math.min(5, Math.max(0, (value / sm) * 5)));
}

function StarsFive({ value, scaleMax }: { value: number; scaleMax: number }) {
  const n = filledStarsOutOfFive(value, scaleMax);
  return (
    <span className="text-amber-400 text-sm" aria-hidden title={`${value} sobre ${scaleMax}`}>
      {"★".repeat(n)}
      <span className="text-gray-600">{"★".repeat(5 - n)}</span>
    </span>
  );
}

function ProfileThumb({ imageUrl }: { imageUrl: string | null | undefined }) {
  const [broken, setBroken] = useState(false);
  useEffect(() => {
    setBroken(false);
  }, [imageUrl]);

  if (!imageUrl || broken) {
    return (
      <div className="w-full h-full flex items-center justify-center text-gray-500 text-xs bg-white/[0.03]">
        —
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={imageUrl}
      alt=""
      className="w-full h-full object-cover"
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setBroken(true)}
    />
  );
}

export default function DoctorDirectorySearch({ layout = "dialog" }: { layout?: "dialog" | "inline" }) {
  const isInline = layout === "inline";
  const [open, setOpen] = useState(isInline);
  const [q, setQ] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [city, setCity] = useState("");
  const [combineMode, setCombineMode] = useState<"and" | "or">("and");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<SearchResponse | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const qRef = useRef<HTMLInputElement>(null);

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

  const runSearch = async () => {
    const jwt = getToken();
    if (!jwt) {
      setError("Sesión requerida.");
      return;
    }
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const params = new URLSearchParams();
      if (q.trim()) params.set("q", q.trim());
      if (specialty.trim()) params.set("specialty", specialty.trim());
      if (city.trim()) params.set("city", city.trim());
      const activeFields = [q.trim(), specialty.trim(), city.trim()].filter(Boolean).length;
      if (activeFields > 1) params.set("match_mode", combineMode);
      params.set("limit", "20");
      params.set("semantic", "true");
      const res = await fetch(`/api/doctor-directory/search?${params.toString()}`, {
        headers: { Authorization: `Bearer ${jwt}` },
        cache: "no-store",
      });
      const json: SearchResponse = await res.json().catch(() => ({}));
      if (!res.ok) {
        const d: unknown = (json as { detail?: unknown }).detail;
        let msg: string | null = null;
        if (typeof d === "string") msg = d;
        else if (Array.isArray(d))
          msg = d
            .map((x) => (typeof x === "object" && x && "msg" in x ? String((x as { msg?: string }).msg) : ""))
            .filter(Boolean)
            .join("; ");
        setError(msg || `Error ${res.status}`);
        return;
      }
      setData(json);
    } catch {
      setError("Error de red. Intenta de nuevo.");
    } finally {
      setLoading(false);
    }
  };

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
                    Directorio de médicos (México)
                  </h2>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Búsqueda sobre perfiles ingeridos desde fuentes públicas (p. ej.{" "}
                    <a
                      href="https://www.topdoctors.mx/"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-emerald-300 hover:underline"
                    >
                      Top Doctors México
                    </a>
                    ,{" "}
                    <a
                      href="https://www.doctoralia.com.mx/"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-emerald-300 hover:underline"
                    >
                      Doctoralia México
                    </a>
                    ,{" "}
                    <a
                      href="https://www.doctoranytime.mx/"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-emerald-300 hover:underline"
                    >
                      DoctorAnytime México
                    </a>
                    ). Si un médico aparece en varias fuentes, verás un enlace por fuente con su fecha de ingesta.
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
                  void runSearch();
                }}
              >
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <input
                    ref={qRef}
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    placeholder="Nombre o palabras clave"
                    className="rounded-lg bg-[#0a1628] border border-white/15 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
                  />
                  <input
                    value={specialty}
                    onChange={(e) => setSpecialty(e.target.value)}
                    placeholder="Especialidad (contiene)"
                    className="rounded-lg bg-[#0a1628] border border-white/15 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
                  />
                  <input
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                    placeholder="Ciudad / estado"
                    className="rounded-lg bg-[#0a1628] border border-white/15 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
                  />
                </div>
                {[q.trim(), specialty.trim(), city.trim()].filter(Boolean).length >= 2 && (
                  <div className="flex flex-wrap items-center gap-2 text-xs text-gray-400">
                    <span className="text-gray-500">Combinar campos:</span>
                    <label className="inline-flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="radio"
                        name="doctor-dir-combine"
                        checked={combineMode === "and"}
                        onChange={() => setCombineMode("and")}
                        className="accent-emerald-500"
                      />
                      Y (todos)
                    </label>
                    <label className="inline-flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="radio"
                        name="doctor-dir-combine"
                        checked={combineMode === "or"}
                        onChange={() => setCombineMode("or")}
                        className="accent-emerald-500"
                      />
                      O (cualquiera)
                    </label>
                  </div>
                )}
                <p className="text-[10px] text-gray-500 -mt-1">Enter en cualquier campo ejecuta la búsqueda.</p>
                <button
                  type="submit"
                  disabled={loading}
                  className="rounded-lg bg-emerald-600/80 hover:bg-emerald-500 text-white text-sm font-medium px-4 py-2 disabled:opacity-50"
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
                {data && (
                  <>
                    <p className="text-xs text-gray-500">
                      {data.total ?? 0} resultado(s) coincidente(s) (máx. 20 mostrados).
                    </p>
                    {(data.results || []).map((d) => (
                      <article
                        key={d.id}
                        className="rounded-xl border border-white/10 bg-white/[0.04] overflow-hidden"
                      >
                        <div className="flex gap-3 p-3">
                          <div className="shrink-0 w-16 h-16 sm:w-20 sm:h-20 rounded-lg bg-white/5 overflow-hidden border border-white/10">
                            <ProfileThumb imageUrl={d.image_url} />
                          </div>
                          <div className="min-w-0 flex-1">
                            <h3 className="text-sm font-semibold text-white leading-snug">{d.display_name}</h3>
                            <p className="text-xs text-emerald-200/90 mt-0.5">
                              {Array.from(
                                new Set([d.specialty_label, ...(d.specialties_json || [])].filter(Boolean) as string[])
                              )
                                .slice(0, 3)
                                .join(" · ")}
                            </p>
                            {locationLine(d) && (
                              <p className="text-xs text-gray-400 mt-1">{locationLine(d)}</p>
                            )}
                            {d.rating_value != null && (
                              <p className="text-xs text-gray-300 mt-1 flex items-center gap-2 flex-wrap">
                                <StarsFive value={d.rating_value} scaleMax={ratingScaleMax(d)} />
                                <span>
                                  {d.rating_value.toFixed(1)}
                                  {ratingScaleMax(d) > 5 ? ` / ${ratingScaleMax(d)}` : ""}
                                  {d.rating_count != null ? ` · ${d.rating_count} opinión(es) en fuente` : ""}
                                </span>
                              </p>
                            )}
                          </div>
                        </div>
                        {d.street_address && (
                          <div className="px-3 pb-2 text-xs text-gray-400 border-t border-white/5 pt-2">
                            <span className="text-gray-500">Dirección: </span>
                            {d.street_address}
                            {d.postal_code ? `, C.P. ${d.postal_code}` : ""}
                          </div>
                        )}
                        {d.external_reviews_json && d.external_reviews_json.length > 0 && (
                          <div className="px-3 pb-2 border-t border-white/5 pt-2">
                            <p className="text-[10px] uppercase tracking-wide text-gray-500 mb-1">Opiniones de la web</p>
                            <ul className="flex flex-wrap gap-2">
                              {d.external_reviews_json.map((r, i) => {
                                const plat = r.platform || "Otra";
                                const rv = r.rating_value ?? r.rating;
                                const cnt = r.review_count ?? r.count;
                                const mx = r.max_rating ?? 5;
                                return (
                                  <li
                                    key={`${plat}-${i}`}
                                    className="text-xs rounded-md bg-white/5 border border-white/10 px-2 py-1 text-gray-300"
                                  >
                                    {plat}
                                    {rv != null && (
                                      <span className="text-amber-300 ml-1">
                                        {rv}/{mx}
                                        {cnt != null ? ` (${cnt})` : ""}
                                      </span>
                                    )}
                                  </li>
                                );
                              })}
                            </ul>
                          </div>
                        )}
                        {d.services_json && d.services_json.length > 0 && (
                          <div className="px-3 pb-2 flex flex-wrap gap-1">
                            {d.services_json.slice(0, 6).map((s) => (
                              <span key={s} className="text-[10px] rounded bg-white/5 text-gray-400 px-1.5 py-0.5">
                                {s}
                              </span>
                            ))}
                          </div>
                        )}
                        <div className="flex flex-wrap gap-2 px-3 pb-3 pt-1 border-t border-white/5">
                          {(d.source_appearances && d.source_appearances.length > 0
                            ? d.source_appearances
                            : [{ source_site: d.source_site, profile_url: d.profile_url, last_scraped_at: d.last_scraped_at }]
                          ).map((app, idx) => (
                            <a
                              key={`${app.profile_url}-${idx}`}
                              href={app.profile_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs rounded-lg bg-cyan-600/70 hover:bg-cyan-500 text-white px-3 py-1.5"
                              title={
                                app.last_scraped_at
                                  ? `Ingesta: ${new Date(app.last_scraped_at).toLocaleString("es-MX")}`
                                  : undefined
                              }
                            >
                              {app.source_site ? `Ver en ${app.source_site}` : "Ver perfil"}
                            </a>
                          ))}
                          {d.phones_json && d.phones_json[0] && (
                            <a
                              href={`tel:${d.phones_json[0].replace(/[^\d+]/g, "")}`}
                              className="text-xs rounded-lg border border-white/20 text-gray-200 px-3 py-1.5 hover:bg-white/10"
                            >
                              Llamar
                            </a>
                          )}
                        </div>
                        <p className="text-[10px] text-gray-600 px-3 pb-2">
                          {d.source_appearances && d.source_appearances.length > 1
                            ? `Fuentes unificadas (${d.source_site}): ${d.source_appearances
                                .map((a) =>
                                  a.last_scraped_at
                                    ? `${a.source_site} @ ${new Date(a.last_scraped_at).toLocaleString("es-MX")}`
                                    : a.source_site,
                                )
                                .join(" · ")}`
                            : `Fuente: ${d.source_site}${
                                d.last_scraped_at
                                  ? ` · Ingesta: ${new Date(d.last_scraped_at).toLocaleString("es-MX")}`
                                  : ""
                              }`}
                        </p>
                      </article>
                    ))}
                  </>
                )}
              </div>

              <div className="px-4 py-2 border-t border-white/10 bg-black/20">
                <p className="text-[10px] text-gray-500 leading-snug">
                  {data?.disclaimer ||
                    "Los datos provienen de sitios de terceros; verifica siempre en la fuente antes de agendar o citar."}
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
        className="flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/5 px-2.5 py-1.5 text-xs text-gray-200 hover:border-emerald-500/40 hover:bg-white/10 hover:text-white transition-colors md:px-3"
        title="Buscar médicos en el directorio ingerido (México)"
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        <svg className="w-4 h-4 text-emerald-300 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
          />
        </svg>
        <span className="hidden sm:inline max-w-[10rem] truncate">Directorio MX</span>
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
          document.body
        )}
    </>
  );
}
