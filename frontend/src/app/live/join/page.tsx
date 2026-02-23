"use client";

import { useCallback, useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";

function LiveJoinContent() {
  const searchParams = useSearchParams();
  const room = searchParams.get("room");
  const token = searchParams.get("token");
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [scriptLoaded, setScriptLoaded] = useState(false);

  const joinCall = useCallback(async () => {
    if (!room || !containerRef.current) return;
    const DailyLib = (window as unknown as {
      Daily?: { createFrame: (parent?: HTMLElement, opts?: { iframeStyle?: Record<string, string> }) => { on: (e: string, cb: (ev?: unknown) => void) => void; join: (opts: { url: string; token?: string }) => Promise<void> } };
    }).Daily;
    if (!DailyLib) return;
    const prefix = "[LiveAvatar]";
    try {
      const callFrame = DailyLib.createFrame(containerRef.current, {
        iframeStyle: { width: "100%", height: "100%", border: "0" },
      });
      // Debug logs for connection and audio
      callFrame.on("joined-meeting", () => console.log(prefix, "joined-meeting"));
      callFrame.on("participant-joined", (e) => {
        const p = (e as { participant?: { local?: boolean; user_name?: string } })?.participant;
        console.log(prefix, "participant-joined", p?.user_name || (p?.local ? "me" : "remote"));
      });
      callFrame.on("participant-left", (e) => console.log(prefix, "participant-left", e));
      callFrame.on("track-started", (e) => {
        const ev = e as { participant?: { local?: boolean }; track?: { kind?: string } };
        console.log(prefix, "track-started", ev?.participant?.local ? "local" : "remote", ev?.track?.kind);
      });
      callFrame.on("track-stopped", (e) => {
        const ev = e as { participant?: { local?: boolean }; track?: { kind?: string } };
        console.log(prefix, "track-stopped", ev?.participant?.local ? "local" : "remote", ev?.track?.kind);
      });
      callFrame.on("error", (e) => console.error(prefix, "error", e));
      callFrame.on("nonfatal-error", (e) => console.warn(prefix, "nonfatal-error", e));
      callFrame.on("app-message", (e) => console.log(prefix, "app-message", e));
      let micLogged = false;
      callFrame.on("local-audio-level", (e) => {
        const ev = e as { level?: number };
        if (!micLogged && ev?.level && ev.level > 0.05) {
          micLogged = true;
          console.log(prefix, "mic detected (audio being sent)");
        }
      });
      await callFrame.join({
        url: room,
        token: token || undefined,
      });
      console.log(prefix, "room connected, room:", room?.slice(0, 30) + "...");
    } catch (e) {
      setError(String(e));
    }
  }, [room, token]);

  useEffect(() => {
    if (!room) {
      setError("Falta el parámetro room");
      return;
    }
    if ((window as unknown as { Daily?: unknown }).Daily) {
      setScriptLoaded(true);
      return;
    }
    const script = document.createElement("script");
    script.src = "https://unpkg.com/@daily-co/daily-js";
    script.async = true;
    script.onload = () => setScriptLoaded(true);
    document.head.appendChild(script);
    return () => {
      script.remove();
    };
  }, [room]);

  useEffect(() => {
    if (scriptLoaded && room) {
      joinCall();
    }
  }, [scriptLoaded, room, joinCall]);

  if (!room) {
    return (
      <div className="min-h-screen bg-[#0a1628] flex items-center justify-center p-4">
        <p className="text-red-400">URL inválida. Usa el botón en /live para iniciar una sesión.</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#0a1628] flex items-center justify-center p-4">
        <p className="text-red-400">{error}</p>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 bg-[#0a1628] flex flex-col">
      <div className="flex-1 min-h-0" ref={containerRef} />
    </div>
  );
}

export default function LiveJoinPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#0a1628] flex items-center justify-center"><p className="text-gray-400">Cargando...</p></div>}>
      <LiveJoinContent />
    </Suspense>
  );
}
