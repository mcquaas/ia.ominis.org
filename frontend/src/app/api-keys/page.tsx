'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/hooks/useAuth';
import Header from '@/components/Header';
import Link from 'next/link';
import {
  getApiKeys,
  createApiKey,
  revokeApiKey,
  getApiKeyRecentRequests,
} from '@/services/auth';
import type { ApiKey, ApiKeyRecentRequest } from '@/types/auth';

/* ── status badge ── */
function StatusBadge({ status }: { status: string }) {
  const cls: Record<string, string> = {
    active: 'bg-green-500/20 text-green-300 border-green-500/30',
    revoked: 'bg-red-500/20 text-red-300 border-red-500/30',
    expired: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  };
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs rounded-full border ${cls[status] || cls.active}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${status === 'active' ? 'bg-green-400' : status === 'revoked' ? 'bg-red-400' : 'bg-gray-400'}`} />
      {status}
    </span>
  );
}

/* ── copy button ── */
function MagnifyIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
    </svg>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button onClick={copy} className="text-gray-400 hover:text-white transition-colors" title="Copiar">
      {copied ? (
        <svg className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
      ) : (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
      )}
    </button>
  );
}

/* ════════════════════════════════════════════════ */
export default function ApiKeysPage() {
  const { user, loading: authLoading, isAuthenticated } = useAuth();

  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');

  /* create form */
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [creating, setCreating] = useState(false);
  const [newKeySecret, setNewKeySecret] = useState(''); // shown once

  /* recent requests modal */
  const [recentModalKey, setRecentModalKey] = useState<ApiKey | null>(null);
  const [recentRows, setRecentRows] = useState<ApiKeyRecentRequest[]>([]);
  const [recentLoading, setRecentLoading] = useState(false);
  const [recentErr, setRecentErr] = useState('');

  const openRecentModal = async (k: ApiKey) => {
    setRecentModalKey(k);
    setRecentLoading(true);
    setRecentErr('');
    setRecentRows([]);
    try {
      const data = await getApiKeyRecentRequests(k.id);
      setRecentRows(data);
    } catch (e) {
      setRecentErr(e instanceof Error ? e.message : 'No se pudieron cargar las solicitudes');
    } finally {
      setRecentLoading(false);
    }
  };

  const closeRecentModal = () => {
    setRecentModalKey(null);
    setRecentRows([]);
    setRecentErr('');
  };

  /* ── load keys ── */
  const loadKeys = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getApiKeys();
      setKeys(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al cargar API keys');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authLoading && isAuthenticated) loadKeys();
  }, [authLoading, isAuthenticated, loadKeys]);

  /* ── create key ── */
  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setError('');
    try {
      const res = await createApiKey({ name: newName.trim(), description: newDesc.trim() || undefined });
      setNewKeySecret(res.apiKey);
      setNewName('');
      setNewDesc('');
      setMsg('API key creada exitosamente. Guarda la clave, no se mostrará de nuevo.');
      loadKeys();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al crear API key');
    } finally {
      setCreating(false);
    }
    setTimeout(() => setMsg(''), 8000);
  };

  /* ── revoke key ── */
  const handleRevoke = async (id: number, name: string) => {
    if (!confirm(`¿Revocar la API key "${name}"? Esta acción es irreversible.`)) return;
    try {
      await revokeApiKey(id);
      setMsg('API key revocada');
      loadKeys();
    } catch {
      setError('Error al revocar');
    }
    setTimeout(() => setMsg(''), 4000);
  };

  /* ── guard ── */
  if (authLoading) {
    return <div className="min-h-screen bg-[#0a1628] flex items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-400" /></div>;
  }
  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-[#0a1628] flex flex-col">
        <Header />
        <div className="flex-1 flex items-center justify-center pt-16">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-red-400">Acceso Denegado</h1>
            <p className="mt-2 text-gray-400">Inicia sesión para gestionar tus API keys.</p>
            <Link href="/login" className="mt-4 inline-block text-cyan-400 hover:underline">Iniciar Sesión</Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a1628]">
      <Header />

      {/* ── últimas solicitudes modal ── */}
      {recentModalKey && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="recent-requests-title"
          onClick={(e) => e.target === e.currentTarget && closeRecentModal()}
        >
          <div className="w-full max-w-4xl max-h-[90vh] flex flex-col rounded-xl border border-white/15 bg-[#0c1a30] shadow-2xl shadow-black/50">
            <div className="flex items-start justify-between gap-3 px-5 py-4 border-b border-white/10 shrink-0">
              <div>
                <h2 id="recent-requests-title" className="text-white font-semibold text-sm">
                  Últimas solicitudes
                </h2>
                <p className="text-gray-500 text-xs mt-0.5">
                  {recentModalKey.name} · hasta 5 registros (petición y respuesta)
                </p>
              </div>
              <button
                type="button"
                onClick={closeRecentModal}
                className="shrink-0 p-2 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
                aria-label="Cerrar"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>

            <div className="overflow-y-auto flex-1 px-5 py-4 space-y-4">
              {recentLoading && (
                <div className="flex justify-center py-12">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-400" />
                </div>
              )}
              {recentErr && !recentLoading && (
                <div className="p-3 rounded-lg bg-red-500/15 border border-red-500/25 text-red-300 text-sm">{recentErr}</div>
              )}
              {!recentLoading && !recentErr && recentRows.length === 0 && (
                <p className="text-gray-500 text-sm text-center py-10">
                  Aún no hay solicitudes registradas con esta clave. Las peticiones a{' '}
                  <code className="text-cyan-400/90">/v1/query</code> y rutas relacionadas aparecerán aquí.
                </p>
              )}
              {!recentLoading &&
                recentRows.map((row) => (
                  <div
                    key={row.id}
                    className="rounded-lg border border-white/10 bg-black/20 overflow-hidden"
                  >
                    <div className="px-3 py-2 bg-white/5 flex flex-wrap items-center gap-2 text-xs">
                      <span className="text-gray-300 font-mono">
                        {new Date(row.createdAt).toLocaleString('es-MX', {
                          dateStyle: 'short',
                          timeStyle: 'medium',
                        })}
                      </span>
                      <span className="text-cyan-400/90">{row.method}</span>
                      <span className="text-gray-500 truncate max-w-[200px] sm:max-w-md" title={row.path}>
                        {row.path}
                      </span>
                      <span
                        className={
                          row.statusCode >= 400
                            ? 'text-red-400'
                            : row.statusCode >= 300
                              ? 'text-amber-400'
                              : 'text-green-400'
                        }
                      >
                        {row.statusCode}
                      </span>
                      {row.streamResponse && (
                        <span className="px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/20">
                          streaming
                        </span>
                      )}
                      {row.requestTruncated && (
                        <span className="px-1.5 py-0.5 rounded bg-orange-500/15 text-orange-200 border border-orange-500/20">
                          petición truncada
                        </span>
                      )}
                      {row.responseTruncated && (
                        <span className="px-1.5 py-0.5 rounded bg-orange-500/15 text-orange-200 border border-orange-500/20">
                          respuesta truncada
                        </span>
                      )}
                    </div>
                    <div className="grid md:grid-cols-2 gap-0 divide-y md:divide-y-0 md:divide-x divide-white/10">
                      <div className="p-3 min-h-[120px]">
                        <p className="text-[10px] uppercase tracking-wide text-gray-500 mb-1.5">Petición</p>
                        <pre className="text-[11px] leading-relaxed text-green-300/95 font-mono whitespace-pre-wrap break-words max-h-64 overflow-y-auto">
                          {row.request || '—'}
                        </pre>
                      </div>
                      <div className="p-3 min-h-[120px]">
                        <p className="text-[10px] uppercase tracking-wide text-gray-500 mb-1.5">Respuesta</p>
                        <pre className="text-[11px] leading-relaxed text-sky-300/95 font-mono whitespace-pre-wrap break-words max-h-64 overflow-y-auto">
                          {row.response || '—'}
                        </pre>
                      </div>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        </div>
      )}

      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-12">
        {/* header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-white">API Keys</h1>
            <p className="text-gray-400 text-sm mt-1">Crea y gestiona claves de acceso para la API de Ominis</p>
          </div>
          <button
            onClick={() => { setShowCreate(!showCreate); setNewKeySecret(''); }}
            className="flex items-center gap-2 bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
            Nueva API Key
          </button>
        </div>

        {/* alerts */}
        {error && <div className="mb-4 p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-300 text-sm">{error}</div>}
        {msg && <div className="mb-4 p-3 bg-green-500/20 border border-green-500/30 rounded-lg text-green-300 text-sm">{msg}</div>}

        {/* ── new key shown once ── */}
        {newKeySecret && (
          <div className="mb-6 p-4 bg-amber-500/10 border border-amber-500/30 rounded-xl">
            <div className="flex items-start gap-3">
              <svg className="w-5 h-5 text-amber-400 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              <div className="min-w-0 flex-1">
                <p className="text-amber-300 font-medium text-sm">Guarda esta clave — no se mostrará de nuevo</p>
                <div className="mt-2 flex items-center gap-2 bg-black/30 rounded-lg px-3 py-2">
                  <code className="text-green-300 text-xs font-mono break-all flex-1 select-all">{newKeySecret}</code>
                  <CopyButton text={newKeySecret} />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── create form ── */}
        {showCreate && (
          <div className="mb-6 bg-white/5 border border-white/10 rounded-xl p-5">
            <h2 className="text-white font-semibold text-sm mb-4">Crear nueva API Key</h2>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-gray-400 text-xs mb-1">Nombre *</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Mi aplicación"
                  required
                  className="w-full bg-white/5 border border-white/10 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500/50 placeholder-gray-500"
                />
              </div>
              <div>
                <label className="block text-gray-400 text-xs mb-1">Descripción (opcional)</label>
                <input
                  type="text"
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  placeholder="Para uso interno de investigación"
                  className="w-full bg-white/5 border border-white/10 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500/50 placeholder-gray-500"
                />
              </div>
              <div className="flex gap-3">
                <button
                  type="submit"
                  disabled={creating || !newName.trim()}
                  className="bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
                >
                  {creating ? 'Creando...' : 'Crear API Key'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="bg-white/10 hover:bg-white/15 text-gray-300 text-sm px-4 py-2 rounded-lg transition-colors"
                >
                  Cancelar
                </button>
              </div>
            </form>
          </div>
        )}

        {/* ── keys list ── */}
        <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-white/10 bg-white/5">
            <h2 className="text-white font-semibold text-sm">Tus API Keys ({keys.length})</h2>
          </div>

          {loading ? (
            <div className="p-8 flex justify-center"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-cyan-400" /></div>
          ) : keys.length === 0 ? (
            <div className="p-8 text-center">
              <svg className="w-12 h-12 text-gray-600 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" /></svg>
              <p className="text-gray-400 text-sm">No tienes API keys aún.</p>
              <p className="text-gray-500 text-xs mt-1">Crea una para acceder a la API de Ominis desde tus aplicaciones.</p>
            </div>
          ) : (
            <div className="divide-y divide-white/5">
              {keys.map((k) => (
                <div key={k.id} className="px-5 py-4 hover:bg-white/[0.02] transition-colors">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-white font-medium text-sm">{k.name}</h3>
                        <StatusBadge status={k.status} />
                      </div>
                      <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-500 flex-wrap">
                        <span className="font-mono text-gray-400">{k.keyPrefix}...</span>
                        <span>Creada: {new Date(k.createdAt).toLocaleDateString('es-MX')}</span>
                        {k.lastUsedAt && <span>Último uso: {new Date(k.lastUsedAt).toLocaleDateString('es-MX')}</span>}
                        <span className="inline-flex items-center gap-1">
                          Solicitudes: {k.requestsCount}
                          <button
                            type="button"
                            onClick={() => void openRecentModal(k)}
                            className="inline-flex p-0.5 rounded text-gray-500 hover:text-cyan-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/50 transition-colors"
                            title="Ver últimas solicitudes (petición y respuesta)"
                            aria-label={`Ver últimas solicitudes para ${k.name}`}
                          >
                            <MagnifyIcon className="w-3.5 h-3.5" />
                          </button>
                        </span>
                        {k.expiresAt && <span>Expira: {new Date(k.expiresAt).toLocaleDateString('es-MX')}</span>}
                      </div>
                      {/* permissions */}
                      <div className="flex gap-1.5 mt-2">
                        {k.permissions?.query && <span className="px-2 py-0.5 text-[10px] rounded bg-cyan-500/15 text-cyan-300 border border-cyan-500/20">query</span>}
                        {k.permissions?.queryGpu && <span className="px-2 py-0.5 text-[10px] rounded bg-blue-500/15 text-blue-300 border border-blue-500/20">query-gpu</span>}
                        {k.permissions?.sources && <span className="px-2 py-0.5 text-[10px] rounded bg-purple-500/15 text-purple-300 border border-purple-500/20">sources</span>}
                      </div>
                    </div>

                    {/* actions */}
                    {k.status === 'active' && (
                      <button
                        onClick={() => handleRevoke(k.id, k.name)}
                        className="shrink-0 px-3 py-1.5 text-xs rounded-lg bg-red-500/15 text-red-300 border border-red-500/20 hover:bg-red-500/25 transition-colors"
                      >
                        Revocar
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── usage info ── */}
        <div className="mt-6 bg-white/5 border border-white/10 rounded-xl p-5">
          <h2 className="text-white font-semibold text-sm mb-3">Cómo usar tu API Key</h2>
          <div className="space-y-3">
            <div>
              <p className="text-gray-400 text-xs mb-1.5">Incluye la clave en el header de tus peticiones:</p>
              <div className="bg-black/30 rounded-lg px-4 py-3 flex items-center gap-2">
                <code className="text-green-300 text-xs font-mono flex-1">Authorization: Bearer ominis_tu_clave_aqui</code>
                <CopyButton text="Authorization: Bearer ominis_tu_clave_aqui" />
              </div>
            </div>
            <div>
              <p className="text-gray-400 text-xs mb-1.5">Ejemplo con curl:</p>
              <div className="bg-black/30 rounded-lg px-4 py-3">
                <code className="text-green-300 text-xs font-mono block whitespace-pre-wrap">{`curl -X POST https://api.ominis.org/v1/query \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ominis_tu_clave" \\
  -d '{"question": "¿Qué es la diabetes?"}'`}</code>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
