"use client";

import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";

type Mode = "heygen" | "pipecat";

export default function LivePage() {
  const { user, loading: authLoading, isAdmin } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [joinUrl, setJoinUrl] = useState<string | null>(null);

  const handleConnect = async (mode: Mode) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/liveavatar/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || data.detail || "No se pudo crear la sesión");
        return;
      }
      if (data.join_url) {
        setJoinUrl(data.join_url);
        // Navigate in same tab — most reliable, avoids popup blockers
        window.location.href = data.join_url;
      } else {
        setError(data.message || "Respuesta inválida del servidor");
      }
    } catch (e) {
      setError("Error de conexión. Verifica que el backend esté activo.");
    } finally {
      setLoading(false);
    }
  };

  if (!authLoading && !isAdmin) {
    return (
      <div className="max-w-2xl mx-auto text-center py-16">
        <p className="text-gray-400">Necesitas permisos de administrador para acceder a Live Avatar.</p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="text-center mb-10">
        <h1 className="text-2xl sm:text-3xl font-bold text-white mb-2">
          Live Avatar
        </h1>
        <p className="text-gray-400 text-sm sm:text-base">
          Experimento: asistentes de IA con avatar en tiempo real
        </p>
      </div>

      <div className="bg-[#0f1d32]/60 border border-white/10 rounded-2xl p-6 sm:p-8">
        <p className="text-gray-300 text-sm leading-relaxed mb-6">
          Prueba primero con HeyGen (LLM por defecto) para verificar conexión.
          Luego con Ominis Med (BioMistral) para el asistente clínico.
        </p>

        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-xl text-red-300 text-sm">
            {error}
          </div>
        )}

        <div className="flex flex-col sm:flex-row gap-3">
          <button
            onClick={() => handleConnect("heygen")}
            disabled={loading}
            className="flex-1 py-3 px-6 bg-emerald-500 hover:bg-emerald-400 disabled:bg-emerald-500/50 disabled:cursor-not-allowed text-[#0a1628] font-semibold rounded-xl transition-colors flex items-center justify-center gap-2"
          >
            {loading ? (
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            ) : (
              <>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                HeyGen (default)
              </>
            )}
          </button>
          <button
            onClick={() => handleConnect("pipecat")}
            disabled={loading}
            className="flex-1 py-3 px-6 bg-cyan-500 hover:bg-cyan-400 disabled:bg-cyan-500/50 disabled:cursor-not-allowed text-[#0a1628] font-semibold rounded-xl transition-colors flex items-center justify-center gap-2"
          >
            {loading ? (
              <span className="opacity-70">...</span>
            ) : (
              <>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
                Ominis (BioMistral)
              </>
            )}
          </button>
        </div>

        {joinUrl && !error && (
          <p className="mt-4 text-gray-500 text-xs text-center">
            Se abrió una nueva ventana. Si no la ves,{" "}
            <a href={joinUrl} target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:underline">
              haz clic aquí
            </a>
            .
          </p>
        )}
      </div>

      <p className="mt-8 text-gray-500 text-xs text-center">
        Pipecat: PIPECAT_AGENT_NAME + PIPECAT_API_TOKEN (BioMistral). HeyGen: HEYGEN_LIVE_AVATAR_API_KEY.
      </p>
    </div>
  );
}
