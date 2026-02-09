"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import type { ConversationSummary } from "@/services/chat";

interface ChatSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onOpen: () => void;
  isAuthenticated: boolean;
  conversations: ConversationSummary[];
  activeConversationId: number | null;
  onSelectConversation: (uuid: string) => void;
  onNewChat: () => void;
  onDeleteConversation: (id: number) => void;
  onRenameConversation: (id: number, newTitle: string) => void;
  onRegenerateTitle: (id: number) => void;
  historyEnabled: boolean;
  onToggleHistory: (enabled: boolean) => void;
}

/** Format a timestamp as relative time. */
function formatRelativeTime(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMs / 3600000);

  const isToday = d.toDateString() === now.toDateString();

  if (isToday) {
    if (diffMin < 1) return "ahora";
    if (diffMin < 60) return `hace ${diffMin} min`;
    return `hace ${diffHr}h ${diffMin % 60}min`;
  }

  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) {
    return `ayer ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
  }

  return `${d.getDate()}/${d.getMonth() + 1} ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}

/** Group conversations by date label. */
function groupByDate(conversations: ConversationSummary[]) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const weekAgo = new Date(today);
  weekAgo.setDate(weekAgo.getDate() - 7);
  const monthAgo = new Date(today);
  monthAgo.setDate(monthAgo.getDate() - 30);

  const groups: { label: string; items: ConversationSummary[] }[] = [
    { label: "Hoy", items: [] },
    { label: "Ayer", items: [] },
    { label: "Últimos 7 días", items: [] },
    { label: "Últimos 30 días", items: [] },
    { label: "Más antiguos", items: [] },
  ];

  for (const conv of conversations) {
    const d = new Date(conv.updated_at);
    if (d >= today) groups[0].items.push(conv);
    else if (d >= yesterday) groups[1].items.push(conv);
    else if (d >= weekAgo) groups[2].items.push(conv);
    else if (d >= monthAgo) groups[3].items.push(conv);
    else groups[4].items.push(conv);
  }

  return groups.filter((g) => g.items.length > 0);
}

export default function ChatSidebar({
  isOpen,
  onClose,
  onOpen,
  isAuthenticated,
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
  onRenameConversation,
  onRegenerateTitle,
  historyEnabled,
  onToggleHistory,
}: ChatSidebarProps) {
  const [menuOpenId, setMenuOpenId] = useState<number | null>(null);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);

  // Close popup menu on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpenId(null);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Focus rename input
  useEffect(() => {
    if (renamingId !== null) {
      renameInputRef.current?.focus();
      renameInputRef.current?.select();
    }
  }, [renamingId]);

  const startRename = (conv: ConversationSummary) => {
    setRenamingId(conv.id);
    setRenameValue(conv.title);
    setMenuOpenId(null);
  };

  const submitRename = () => {
    if (renamingId !== null && renameValue.trim()) {
      onRenameConversation(renamingId, renameValue.trim());
    }
    setRenamingId(null);
    setRenameValue("");
  };

  const handleDelete = (id: number) => {
    setConfirmDeleteId(null);
    setMenuOpenId(null);
    onDeleteConversation(id);
  };

  const grouped = groupByDate(conversations);

  return (
    <>
      {/* Overlay for mobile */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Collapsed mini-bar (visible when sidebar is closed on desktop) */}
      {!isOpen && (
        <div className="hidden lg:flex fixed top-16 left-0 bottom-0 z-40 w-10 bg-[#0b1426]/80 backdrop-blur-sm border-r border-white/10 flex-col items-center py-3 gap-2">
          <button
            onClick={onOpen}
            className="text-gray-400 hover:text-white p-1.5 hover:bg-white/10 rounded-lg transition-colors"
            title="Abrir historial"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          {isAuthenticated && (
            <button
              onClick={onNewChat}
              className="text-gray-400 hover:text-white p-1.5 hover:bg-white/10 rounded-lg transition-colors"
              title="Nuevo trabajo"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </button>
          )}
        </div>
      )}

      {/* Sidebar */}
      <aside
        className={`fixed top-16 left-0 bottom-0 z-40 w-72 bg-[#0b1426]/95 backdrop-blur-md border-r border-white/10 flex flex-col transition-transform duration-300 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
          {isAuthenticated ? (
            <button
              onClick={onNewChat}
              className="flex items-center gap-2 text-sm text-white hover:text-blue-400 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Nuevo trabajo
            </button>
          ) : (
            <span className="text-sm text-gray-400">Trabajos</span>
          )}
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white p-1 transition-colors"
            title="Cerrar sidebar"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
        </div>

        {/* Content */}
        {!isAuthenticated ? (
          /* Not logged in message */
          <div className="flex-1 flex flex-col items-center justify-center px-6 text-center">
            <svg className="w-10 h-10 text-gray-600 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <p className="text-gray-400 text-sm mb-2">
              Inicia sesión para guardar y ver tu historial de trabajos.
            </p>
            <Link
              href="/login"
              className="text-blue-400 hover:text-blue-300 text-sm font-medium transition-colors"
            >
              Iniciar sesión →
            </Link>
          </div>
        ) : (
        <>
        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto py-2">
          {conversations.length === 0 ? (
            <p className="text-gray-500 text-xs text-center mt-8 px-4">
              No tienes trabajos guardados.
            </p>
          ) : (
            grouped.map((group) => (
              <div key={group.label} className="mb-2">
                <p className="px-4 py-1.5 text-[10px] uppercase tracking-wider text-gray-500 font-semibold">
                  {group.label}
                </p>
                {group.items.map((conv) => (
                  <div
                    key={conv.id}
                    className={`group relative flex items-center px-3 mx-2 rounded-lg transition-colors ${
                      conv.id === activeConversationId
                        ? "bg-white/10 text-white"
                        : "text-gray-300 hover:bg-white/5 hover:text-white"
                    }`}
                  >
                    {renamingId === conv.id ? (
                      <input
                        ref={renameInputRef}
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") submitRename();
                          if (e.key === "Escape") { setRenamingId(null); setRenameValue(""); }
                        }}
                        onBlur={submitRename}
                        className="flex-1 bg-white/10 border border-white/20 rounded px-2 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500 my-0.5"
                      />
                    ) : (
                      <Link
                        href={`/c/${conv.uuid}`}
                        onClick={(e) => { e.preventDefault(); onSelectConversation(conv.uuid); }}
                        className="flex-1 block py-1.5 pr-6 min-w-0 cursor-pointer"
                        title={conv.title}
                      >
                        <span className="text-sm leading-snug line-clamp-2">{conv.title}</span>
                        <span className="text-[10px] text-gray-500 block mt-0.5">{formatRelativeTime(conv.updated_at)}</span>
                      </Link>
                    )}

                    {/* 3-dot menu button */}
                    {renamingId !== conv.id && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setMenuOpenId(menuOpenId === conv.id ? null : conv.id);
                          setConfirmDeleteId(null);
                        }}
                        className="absolute right-2 opacity-100 md:opacity-0 md:group-hover:opacity-100 text-gray-400 hover:text-white p-1 transition-opacity"
                        title="Opciones"
                      >
                        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                          <path d="M10 6a2 2 0 110-4 2 2 0 010 4zm0 6a2 2 0 110-4 2 2 0 010 4zm0 6a2 2 0 110-4 2 2 0 010 4z" />
                        </svg>
                      </button>
                    )}

                    {/* Popup menu */}
                    {menuOpenId === conv.id && (
                      <div
                        ref={menuRef}
                        className="absolute right-0 top-full mt-1 w-44 bg-[#1a2744] border border-white/10 rounded-xl shadow-xl py-1 z-50"
                      >
                        <button
                          onClick={() => {
                            const url = `${typeof window !== "undefined" ? window.location.origin : ""}/c/${conv.uuid}`;
                            navigator.clipboard.writeText(url);
                            setMenuOpenId(null);
                          }}
                          className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-300 hover:bg-white/10 hover:text-white transition-colors"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                          </svg>
                          Copiar enlace
                        </button>
                        <button
                          onClick={() => startRename(conv)}
                          className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-300 hover:bg-white/10 hover:text-white transition-colors"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                          </svg>
                          Renombrar
                        </button>
                        <button
                          onClick={() => { onRegenerateTitle(conv.id); setMenuOpenId(null); }}
                          className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-300 hover:bg-white/10 hover:text-white transition-colors"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                          </svg>
                          Regenerar título
                        </button>
                        {confirmDeleteId === conv.id ? (
                          <div className="px-3 py-2">
                            <p className="text-xs text-red-400 mb-2">¿Eliminar esta investigación?</p>
                            <div className="flex gap-2">
                              <button
                                onClick={() => handleDelete(conv.id)}
                                className="flex-1 bg-red-600 hover:bg-red-500 text-white text-xs py-1 rounded transition-colors"
                              >
                                Eliminar
                              </button>
                              <button
                                onClick={() => setConfirmDeleteId(null)}
                                className="flex-1 bg-white/10 hover:bg-white/20 text-gray-300 text-xs py-1 rounded transition-colors"
                              >
                                Cancelar
                              </button>
                            </div>
                          </div>
                        ) : (
                          <button
                            onClick={() => setConfirmDeleteId(conv.id)}
                            className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-white/10 hover:text-red-300 transition-colors"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                            Eliminar
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ))
          )}
        </div>

        {/* Save history toggle */}
        <div className="border-t border-white/10 px-4 py-3">
          <button
            onClick={() => onToggleHistory(!historyEnabled)}
            className="w-full flex items-center justify-between text-sm text-gray-300"
          >
              <span className="flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Guardar historia
            </span>
            <div
              className={`w-8 h-5 rounded-full transition-colors ${
                historyEnabled ? "bg-blue-500" : "bg-gray-600"
              } relative`}
            >
              <div
                className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${
                  historyEnabled ? "translate-x-3.5" : "translate-x-0.5"
                }`}
              />
            </div>
          </button>
          <p className="text-[10px] text-gray-500 mt-1">
            {historyEnabled
              ? "Se guardará en tu perfil. Nadie tendrá acceso a ella"
              : "La historia no se guardará."}
          </p>
        </div>
        </>
        )}
      </aside>
    </>
  );
}
