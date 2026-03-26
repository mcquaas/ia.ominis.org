"use client";

import { useState } from "react";
import Link from "next/link";
import { getToken } from "@/services/auth";

type AssistResponse = {
  answer?: string;
  sources?: Array<{ title?: string; url?: string; sourceType?: string; nctId?: string }>;
  keywords_used?: string;
  studies_fetched?: number;
  model?: string;
  detail?: string;
};

export default function ClinicalTrialsAssistClient() {
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AssistResponse | null>(null);

  const run = async () => {
    const token = getToken();
    if (!token) {
      setError("Inicia sesión para usar esta herramienta.");
      return;
    }
    const question = q.trim();
    if (question.length < 3) {
      setError("Escribe al menos 3 caracteres.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/clinical-trials/assist", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ question }),
        cache: "no-store",
      });
      const data = (await res.json()) as AssistResponse;
      if (!res.ok) {
        setError(typeof data.detail === "string" ? data.detail : `Error ${res.status}`);
        return;
      }
      setResult(data);
    } catch {
      setError("Error de red. Intenta de nuevo.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <p className="text-sm text-gray-400">
        Pregunta en español: el backend traduce términos para ClinicalTrials.gov y filtra por México. También puedes activar{" "}
        <strong className="text-gray-300">Ensayos (México)</strong> en el menú + del chat para usar la misma fuente en conversación.
      </p>
      <div className="flex flex-col sm:flex-row gap-2">
        <textarea
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ej.: ensayos de vacunas contra dengue reclutando en CDMX"
          rows={3}
          className="flex-1 rounded-xl bg-[#0a1628] border border-white/15 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-teal-500/40"
        />
        <button
          type="button"
          onClick={() => void run()}
          disabled={loading}
          className="shrink-0 rounded-xl bg-teal-600/90 hover:bg-teal-500 text-white text-sm font-medium px-5 py-2 disabled:opacity-50 h-fit"
        >
          {loading ? "Consultando…" : "Consultar"}
        </button>
      </div>
      {error && (
        <p className="text-sm text-red-300" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div className="rounded-xl border border-white/10 bg-white/[0.04] p-4 space-y-3">
          {result.keywords_used != null && (
            <p className="text-[10px] text-gray-500">
              Palabras clave (inglés): <span className="text-gray-400">{result.keywords_used}</span> · Estudios recuperados:{" "}
              {result.studies_fetched ?? "—"}
            </p>
          )}
          <div className="prose prose-invert prose-sm max-w-none whitespace-pre-wrap text-gray-200">{result.answer}</div>
          {result.sources && result.sources.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-2">Fuentes</p>
              <ul className="space-y-1 text-sm">
                {result.sources.map((s, i) => (
                  <li key={s.url || i}>
                    <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-teal-300 hover:underline">
                      {s.title || s.nctId || s.url}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      <p className="text-xs text-gray-600">
        <Link href="/tools" className="text-cyan-400 hover:underline">
          Herramientas
        </Link>
        {" · "}
        <Link href="/c" className="text-cyan-400 hover:underline">
          Chat
        </Link>
      </p>
    </div>
  );
}
