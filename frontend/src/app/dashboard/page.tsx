'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/hooks/useAuth';
import Header from '@/components/Header';
import Link from 'next/link';
import {
  getSystemStats,
  getUsers,
  getHealth,
  toggleUserBlock,
  deleteUser,
  updateUser,
  getStoreStats,
  getServerPerformance,
  getGpuServerPerformance,
} from '@/services/auth';
import { listFeedback, REASON_CATEGORIES } from '@/services/feedback';
import type { FeedbackOut } from '@/services/feedback';

const REASON_LABELS: Record<string, string> = Object.fromEntries(REASON_CATEGORIES.map((c) => [c.value, c.label]));
import type { SystemStats, User } from '@/types/auth';

// ---------- tiny stat card ----------
function StatCard({ label, value, sub, color = 'cyan' }: { label: string; value: string | number; sub?: string; color?: string }) {
  const colorMap: Record<string, string> = {
    cyan: 'from-cyan-500/20 to-cyan-600/5 border-cyan-500/30 text-cyan-300',
    green: 'from-green-500/20 to-green-600/5 border-green-500/30 text-green-300',
    amber: 'from-amber-500/20 to-amber-600/5 border-amber-500/30 text-amber-300',
    red: 'from-red-500/20 to-red-600/5 border-red-500/30 text-red-300',
    purple: 'from-purple-500/20 to-purple-600/5 border-purple-500/30 text-purple-300',
    blue: 'from-blue-500/20 to-blue-600/5 border-blue-500/30 text-blue-300',
  };
  return (
    <div className={`bg-gradient-to-br ${colorMap[color]} border rounded-xl p-4`}>
      <p className="text-xs text-gray-400 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  );
}

// ---------- status badge ----------
function StatusBadge({ status }: { status: string }) {
  const s = status?.toLowerCase();
  const cls =
    s === 'online' || s === 'healthy' || s === 'active'
      ? 'bg-green-500/20 text-green-300 border-green-500/30'
      : s === 'degraded' || s === 'pending' || s === 'indexing'
        ? 'bg-amber-500/20 text-amber-300 border-amber-500/30'
        : 'bg-red-500/20 text-red-300 border-red-500/30';
  return <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full border ${cls}`}>
    <span className={`w-1.5 h-1.5 rounded-full ${s === 'online' || s === 'healthy' || s === 'active' ? 'bg-green-400' : s === 'degraded' || s === 'pending' || s === 'indexing' ? 'bg-amber-400 animate-pulse' : 'bg-red-400'}`} />
    {status}
  </span>;
}

// ---------- section wrapper ----------
function Section({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/10 bg-white/5">
        <h2 className="text-white font-semibold text-sm">{title}</h2>
        {action}
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

// =================================================================
export default function DashboardPage() {
  const { user, loading: authLoading, isAdmin, isSuperAdmin } = useAuth();

  const [stats, setStats] = useState<SystemStats | null>(null);
  const [health, setHealth] = useState<{ status: string; model: { version: string; status: string }; servers: Record<string, string> } | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [storeStats, setStoreStats] = useState<{ totalDocuments: number; embeddingModel: string; storageType: string } | null>(null);
  const [serverPerf, setServerPerf] = useState<{
    cpu?: { cores: number; loadAvg1m: number; usagePercent: number };
    memory?: { totalMB: number; usedMB: number; availableMB: number; usagePercent: number };
    disk?: { totalGB: number; usedGB: number; freeGB: number; usagePercent: number };
    gpu?: { name: string; memoryTotalMB: number; memoryUsedMB: number; utilizationPercent: number; temperatureC: number } | null;
    workers?: Array<{ pid: number; cpuPercent: number; memPercent: number; memMB: number }>;
    database?: { activeConnections: number; idleConnections: number; totalConnections: number } | null;
    uptimeHours?: number;
    hostname?: string;
    ip?: string;
    awsInstanceId?: string;
    awsInstanceType?: string;
  } | null>(null);
  const [gpuPerf, setGpuPerf] = useState<{
    status: string;
    ollamaUrl?: string;
    ollamaVersion?: string;
    gpuServerIp?: string;
    models?: Array<{ name: string; sizeGB: number; parameterSize: string; quantization: string }>;
    runningModels?: Array<{ name: string; sizeVramGB: number }>;
    inference?: { latencyMs: number; tokensPerSecond: number; evalCount: number; evalDurationMs: number; loadDurationMs: number; error?: string };
    error?: string;
  } | null>(null);
  const [queryPeriod, setQueryPeriod] = useState<'hour' | 'day' | 'week' | 'month'>('day');
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState('');
  const [actionMsg, setActionMsg] = useState('');

  // Feedback state (admin/superadmin)
  const [feedbackData, setFeedbackData] = useState<FeedbackOut[]>([]);
  const [feedbackTotal, setFeedbackTotal] = useState(0);
  const [feedbackPage, setFeedbackPage] = useState(1);
  const [feedbackRating, setFeedbackRating] = useState<'positive' | 'negative' | undefined>(undefined);
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [feedbackModalItem, setFeedbackModalItem] = useState<FeedbackOut | null>(null);
  const [feedbackModalInfra, setFeedbackModalInfra] = useState<{
    health: typeof health;
    gpuPerf: typeof gpuPerf;
    serverPerf: typeof serverPerf;
  } | null>(null);

  // ---------- fetch everything ----------
  const loadData = useCallback(async () => {
    setLoadingData(true);
    setError('');
    try {
      const [healthRes, statsRes, storeRes, perfRes, gpuRes] = await Promise.allSettled([
        getHealth(),
        getSystemStats(),
        getStoreStats(),
        getServerPerformance(),
        getGpuServerPerformance(),
      ]);

      if (healthRes.status === 'fulfilled') setHealth(healthRes.value as typeof health);
      if (statsRes.status === 'fulfilled') setStats((statsRes.value as { data: SystemStats }).data);
      if (storeRes.status === 'fulfilled') setStoreStats(storeRes.value as typeof storeStats);
      if (perfRes.status === 'fulfilled') setServerPerf(perfRes.value as typeof serverPerf);
      if (gpuRes.status === 'fulfilled') setGpuPerf(gpuRes.value as typeof gpuPerf);

      if (isSuperAdmin) {
        try {
          const u = await getUsers();
          setUsers(Array.isArray(u) ? u : []);
        } catch { /* non-critical */ }
      }

    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error loading data');
    } finally {
      setLoadingData(false);
    }
  }, [isSuperAdmin]);

  const loadFeedback = useCallback(async () => {
    if (!isAdmin) return;
    setFeedbackLoading(true);
    try {
      const fb = await listFeedback(feedbackPage, 50, feedbackRating);
      setFeedbackData(fb.data);
      setFeedbackTotal(fb.total);
    } catch { /* non-critical */ }
    finally { setFeedbackLoading(false); }
  }, [isAdmin, feedbackPage, feedbackRating]);

  const handleOpenFeedbackModal = useCallback(async (f: FeedbackOut) => {
    setFeedbackModalItem(f);
    setFeedbackModalInfra(null);
    try {
      const [hRes, gRes, sRes] = await Promise.allSettled([
        getHealth(),
        getGpuServerPerformance(),
        getServerPerformance(),
      ]);
      setFeedbackModalInfra({
        health: hRes.status === 'fulfilled' ? (hRes.value as typeof health) : null,
        gpuPerf: gRes.status === 'fulfilled' ? (gRes.value as typeof gpuPerf) : null,
        serverPerf: sRes.status === 'fulfilled' ? (sRes.value as typeof serverPerf) : null,
      });
    } catch { /* non-critical */ }
  }, []);

  useEffect(() => {
    if (isAdmin) loadFeedback();
  }, [isAdmin, loadFeedback]);

  useEffect(() => {
    if (!authLoading && isAdmin) loadData();
  }, [authLoading, isAdmin, loadData]);

  // ---------- User actions ----------
  const showMsg = (msg: string) => { setActionMsg(msg); setTimeout(() => setActionMsg(''), 4000); };

  const handleToggleBlock = async (id: number, blocked: boolean) => {
    try { await toggleUserBlock(id, blocked); showMsg(blocked ? 'Usuario bloqueado' : 'Usuario desbloqueado'); loadData(); }
    catch { showMsg('Error al cambiar estado'); }
  };
  const handleDeleteUser = async (id: number, name: string) => {
    if (!confirm(`Eliminar usuario "${name}"? Esta accion es irreversible.`)) return;
    try { await deleteUser(id); showMsg('Usuario eliminado'); loadData(); }
    catch { showMsg('Error al eliminar'); }
  };
  const handleChangeRole = async (id: number, newRole: string) => {
    try { await updateUser(id, { role: newRole } as unknown as Partial<User>); showMsg(`Rol actualizado a ${newRole}`); loadData(); }
    catch { showMsg('Error al cambiar rol'); }
  };

  // ---------- guard ----------
  if (authLoading) return <div className="min-h-screen bg-[#0a1628] flex items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-400" /></div>;
  if (!user || !isAdmin) {
    return (
      <div className="min-h-screen bg-[#0a1628] flex flex-col">
        <Header />
        <div className="flex-1 flex items-center justify-center pt-16">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-red-400">Acceso Denegado</h1>
            <p className="mt-2 text-gray-400">Necesitas permisos de administrador.</p>
            <Link href="/" className="mt-4 inline-block text-cyan-400 hover:underline">Volver al inicio</Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a1628]">
      <Header />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-12">
        {/* Page header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-white">Dashboard del Sistema</h1>
            <p className="text-gray-400 text-sm mt-1">Panel de administracion de Ominis Agent</p>
          </div>
          <button onClick={loadData} disabled={loadingData}
            className="flex items-center gap-2 bg-white/10 hover:bg-white/15 text-white text-sm px-4 py-2 rounded-lg border border-white/10 transition-colors disabled:opacity-50">
            <svg className={`w-4 h-4 ${loadingData ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Actualizar
          </button>
        </div>

        {error && <div className="mb-4 p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-300 text-sm">{error}</div>}
        {actionMsg && <div className="mb-4 p-3 bg-green-500/20 border border-green-500/30 rounded-lg text-green-300 text-sm">{actionMsg}</div>}

        {/* ===== System Health ===== */}
        <section className="mb-6">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatCard label="Estado" value={health?.status || '—'} color={health?.status === 'healthy' ? 'green' : 'red'} />
            <StatCard label="Modelo" value={health?.model?.version || '—'} sub={health?.model?.status} color={health?.model?.status === 'online' ? 'cyan' : 'red'} />
            <StatCard label="Servidor Primario" value={health?.servers?.primary || '—'} color={health?.servers?.primary === 'online' ? 'green' : 'red'} />
            <StatCard label="Consultas 24h" value={stats?.totalQueries24h ?? '—'} color="blue" />
            <StatCard label="Docs en pgvector" value={storeStats?.totalDocuments ?? '—'} sub={storeStats?.storageType} color="purple" />
            <StatCard label="Consultas Mes" value={stats?.totalQueriesMonth ?? '—'} color="amber" />
          </div>
        </section>

        {/* ===== Server Performance ===== */}
        {serverPerf && (
          <section className="mb-6">
            <div className="bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-4">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h3 className="text-sm font-semibold text-white">Rendimiento del servidor de aplicación</h3>
                  <p className="text-[10px] text-gray-500 mt-0.5">
                    {serverPerf.ip && <>{serverPerf.ip}</>}
                    {serverPerf.awsInstanceId && <> · {serverPerf.awsInstanceId}</>}
                    {serverPerf.awsInstanceType && <> ({serverPerf.awsInstanceType})</>}
                  </p>
                </div>
                {serverPerf.uptimeHours != null && (
                  <span className="text-[10px] text-gray-500">Uptime: {serverPerf.uptimeHours}h</span>
                )}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                {/* CPU */}
                {serverPerf.cpu && (
                  <div className="bg-white/5 rounded-xl p-3">
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">CPU ({serverPerf.cpu.cores} cores)</p>
                    <p className={`text-lg font-bold ${serverPerf.cpu.usagePercent > 80 ? 'text-red-400' : serverPerf.cpu.usagePercent > 50 ? 'text-amber-400' : 'text-green-400'}`}>
                      {serverPerf.cpu.usagePercent}%
                    </p>
                    <p className="text-[10px] text-gray-500">Load: {serverPerf.cpu.loadAvg1m}</p>
                  </div>
                )}
                {/* Memory */}
                {serverPerf.memory && (
                  <div className="bg-white/5 rounded-xl p-3">
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Memoria</p>
                    <p className={`text-lg font-bold ${serverPerf.memory.usagePercent > 85 ? 'text-red-400' : serverPerf.memory.usagePercent > 60 ? 'text-amber-400' : 'text-green-400'}`}>
                      {serverPerf.memory.usagePercent}%
                    </p>
                    <p className="text-[10px] text-gray-500">{(serverPerf.memory.usedMB / 1024).toFixed(1)} / {(serverPerf.memory.totalMB / 1024).toFixed(1)} GB</p>
                  </div>
                )}
                {/* Disk */}
                {serverPerf.disk && (
                  <div className="bg-white/5 rounded-xl p-3">
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Disco</p>
                    <p className={`text-lg font-bold ${serverPerf.disk.usagePercent > 90 ? 'text-red-400' : serverPerf.disk.usagePercent > 70 ? 'text-amber-400' : 'text-green-400'}`}>
                      {serverPerf.disk.usagePercent}%
                    </p>
                    <p className="text-[10px] text-gray-500">{serverPerf.disk.usedGB} / {serverPerf.disk.totalGB} GB</p>
                  </div>
                )}
                {/* GPU */}
                {serverPerf.gpu ? (
                  <div className="bg-white/5 rounded-xl p-3">
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">GPU</p>
                    <p className={`text-lg font-bold ${serverPerf.gpu.utilizationPercent > 80 ? 'text-red-400' : serverPerf.gpu.utilizationPercent > 50 ? 'text-amber-400' : 'text-green-400'}`}>
                      {serverPerf.gpu.utilizationPercent}%
                    </p>
                    <p className="text-[10px] text-gray-500">{serverPerf.gpu.name} · {serverPerf.gpu.temperatureC}°C</p>
                    <p className="text-[10px] text-gray-500">{serverPerf.gpu.memoryUsedMB}/{serverPerf.gpu.memoryTotalMB} MB</p>
                  </div>
                ) : (
                  <div className="bg-white/5 rounded-xl p-3">
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">GPU</p>
                    <p className="text-lg font-bold text-gray-600">N/A</p>
                    <p className="text-[10px] text-gray-500">Sin GPU</p>
                  </div>
                )}
                {/* Database */}
                {serverPerf.database && (
                  <div className="bg-white/5 rounded-xl p-3">
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Base de datos</p>
                    <p className="text-lg font-bold text-cyan-400">{serverPerf.database.totalConnections}</p>
                    <p className="text-[10px] text-gray-500">{serverPerf.database.activeConnections} activas · {serverPerf.database.idleConnections} idle</p>
                  </div>
                )}
              </div>
              {/* Workers */}
              {serverPerf.workers && serverPerf.workers.length > 0 && (
                <div className="mt-3 pt-3 border-t border-white/10">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">Workers ({serverPerf.workers.length})</p>
                  <div className="flex flex-wrap gap-2">
                    {serverPerf.workers.map((w) => (
                      <div key={w.pid} className="bg-white/5 rounded-lg px-2.5 py-1.5 text-[11px]">
                        <span className="text-gray-500">PID {w.pid}</span>
                        <span className={`ml-2 ${w.cpuPercent > 50 ? 'text-red-400' : 'text-gray-300'}`}>CPU {w.cpuPercent}%</span>
                        <span className="ml-2 text-gray-400">RAM {w.memMB}MB</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

        {/* ===== GPU Server Performance ===== */}
        {gpuPerf && (
          <section className="mb-6">
            <div className="bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-4">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h3 className="text-sm font-semibold text-white">Servidor GPU / LLM</h3>
                  <p className="text-[10px] text-gray-500 mt-0.5">
                    {gpuPerf.gpuServerIp && <>{gpuPerf.gpuServerIp}</>}
                    {gpuPerf.ollamaVersion && <> · Ollama v{gpuPerf.ollamaVersion}</>}
                  </p>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full ${gpuPerf.status === 'online' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                  {gpuPerf.status}
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                {/* Inference Speed */}
                {gpuPerf.inference && !gpuPerf.inference.error && (
                  <div className="bg-white/5 rounded-xl p-3">
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Velocidad</p>
                    <p className="text-lg font-bold text-cyan-400">{gpuPerf.inference.tokensPerSecond} <span className="text-xs font-normal text-gray-500">tok/s</span></p>
                    <p className="text-[10px] text-gray-500">Latencia: {gpuPerf.inference.latencyMs}ms</p>
                  </div>
                )}
                {gpuPerf.inference?.error && (
                  <div className="bg-white/5 rounded-xl p-3">
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Velocidad</p>
                    <p className="text-sm font-bold text-red-400">Error</p>
                    <p className="text-[10px] text-gray-500 truncate">{gpuPerf.inference.error}</p>
                  </div>
                )}
                {/* Model Load */}
                {gpuPerf.inference && !gpuPerf.inference.error && (
                  <div className="bg-white/5 rounded-xl p-3">
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Carga del modelo</p>
                    <p className="text-lg font-bold text-green-400">{gpuPerf.inference.loadDurationMs} <span className="text-xs font-normal text-gray-500">ms</span></p>
                    <p className="text-[10px] text-gray-500">Eval: {gpuPerf.inference.evalDurationMs}ms</p>
                  </div>
                )}
                {/* Running Models */}
                <div className="bg-white/5 rounded-xl p-3">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Modelos activos</p>
                  <p className="text-lg font-bold text-amber-400">{gpuPerf.runningModels?.length || 0}</p>
                  {gpuPerf.runningModels && gpuPerf.runningModels.length > 0 ? (
                    <p className="text-[10px] text-gray-500">{gpuPerf.runningModels.map(m => `${m.name} (${m.sizeVramGB}GB)`).join(', ')}</p>
                  ) : (
                    <p className="text-[10px] text-gray-500">Ninguno en VRAM</p>
                  )}
                </div>
                {/* Total Models */}
                <div className="bg-white/5 rounded-xl p-3">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Modelos instalados</p>
                  <p className="text-lg font-bold text-purple-400">{gpuPerf.models?.length || 0}</p>
                  <p className="text-[10px] text-gray-500">
                    {gpuPerf.models?.reduce((sum, m) => sum + m.sizeGB, 0).toFixed(1) || 0} GB total
                  </p>
                </div>
              </div>

              {/* Model list */}
              {gpuPerf.models && gpuPerf.models.length > 0 && (
                <div className="mt-3 pt-3 border-t border-white/10">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">Modelos disponibles</p>
                  <div className="flex flex-wrap gap-2">
                    {gpuPerf.models.map((m) => (
                      <div key={m.name} className="bg-white/5 rounded-lg px-2.5 py-1.5 text-[11px]">
                        <span className="text-white font-medium">{m.name}</span>
                        <span className="text-gray-500 ml-2">{m.sizeGB}GB</span>
                        {m.parameterSize && <span className="text-gray-500 ml-1">· {m.parameterSize}</span>}
                        {m.quantization && <span className="text-gray-500 ml-1">· {m.quantization}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

        {/* ===== RAG ===== */}
        <div className="mb-6">
          <Section title="RAG">
            <Link
              href="/rag"
              className="block p-6 text-center bg-white/5 rounded-xl border border-white/10 hover:border-cyan-500/30 hover:bg-white/10 transition-colors"
            >
              <p className="text-white font-medium">Gestión de fuentes RAG</p>
              <p className="text-gray-400 text-sm mt-1">Ingestión, búsqueda y filtrado por taxonomía</p>
            </Link>
          </Section>
        </div>


        {/* ===== User Management (SuperAdmin only) ===== */}
        {isSuperAdmin && (
          <Section title={`Gestion de Usuarios (${users.length})`}>
            {users.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-gray-400 text-xs uppercase border-b border-white/10">
                      <th className="pb-2 pr-4">Usuario</th>
                      <th className="pb-2 pr-4">Email</th>
                      <th className="pb-2 pr-4">Rol</th>
                      <th className="pb-2 pr-4">Estado</th>
                      <th className="pb-2 pr-4">Registrado</th>
                      <th className="pb-2">Acciones</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {users.map((u) => (
                      <tr key={u.id} className="hover:bg-white/5 transition-colors">
                        <td className="py-2.5 pr-4 text-white font-medium">{u.username}</td>
                        <td className="py-2.5 pr-4 text-gray-400">{u.email}</td>
                        <td className="py-2.5 pr-4">
                          <select
                            value={u.role?.type || 'researcher'}
                            onChange={(e) => handleChangeRole(u.id, e.target.value)}
                            disabled={u.id === user?.id}
                            className="bg-white/10 border border-white/10 text-white text-xs rounded px-2 py-1 disabled:opacity-50"
                          >
                            <option value="researcher">researcher</option>
                            <option value="developer">developer</option>
                            <option value="admin">admin</option>
                            <option value="superadmin">superadmin</option>
                          </select>
                        </td>
                        <td className="py-2.5 pr-4"><StatusBadge status={u.blocked ? 'blocked' : 'active'} /></td>
                        <td className="py-2.5 pr-4 text-gray-500 text-xs">{new Date(u.createdAt).toLocaleDateString('es-MX')}</td>
                        <td className="py-2.5">
                          {u.id !== user?.id && (
                            <div className="flex gap-1">
                              <button onClick={() => handleToggleBlock(u.id, !u.blocked)}
                                className={`px-2 py-1 text-xs rounded ${u.blocked ? 'bg-green-500/20 text-green-300 hover:bg-green-500/30' : 'bg-amber-500/20 text-amber-300 hover:bg-amber-500/30'}`}>
                                {u.blocked ? 'Desbloquear' : 'Bloquear'}
                              </button>
                              <button onClick={() => handleDeleteUser(u.id, u.username)}
                                className="px-2 py-1 text-xs rounded bg-red-500/20 text-red-300 hover:bg-red-500/30">
                                Eliminar
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-gray-500 text-sm">Cargando usuarios...</p>
            )}
          </Section>
        )}

        {/* ===== Feedback (Admin / SuperAdmin) ===== */}
        <Section
          title={`Comentarios de usuarios (${feedbackTotal})`}
          action={
            <div className="flex items-center gap-2">
              <div className="flex gap-1">
                {([undefined, 'positive', 'negative'] as const).map((r) => (
                  <button
                    key={r ?? 'all'}
                    onClick={() => { setFeedbackRating(r); setFeedbackPage(1); }}
                    className={`px-2 py-1 text-xs rounded ${feedbackRating === r ? 'bg-cyan-500/30 text-cyan-300' : 'text-gray-400 hover:text-white'}`}
                  >
                    {r === undefined ? 'Todos' : r === 'positive' ? 'Positivos' : 'Negativos'}
                  </button>
                ))}
              </div>
              <button
                onClick={loadFeedback}
                disabled={feedbackLoading}
                className="p-1 text-gray-400 hover:text-white disabled:opacity-50"
                title="Actualizar"
              >
                <svg className={`w-4 h-4 ${feedbackLoading ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </button>
            </div>
          }
        >
          {feedbackData.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-400 text-xs uppercase border-b border-white/10">
                    <th className="pb-2 pr-3">Hora</th>
                    <th className="pb-2 pr-3 w-10"></th>
                    <th className="pb-2 pr-3">Modelo</th>
                    <th className="pb-2 pr-3">Usuario</th>
                    <th className="pb-2">Título</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {feedbackData.map((f) => (
                    <tr
                      key={f.id}
                      onClick={() => handleOpenFeedbackModal(f)}
                      className="hover:bg-white/10 cursor-pointer transition-colors"
                    >
                      <td className="py-2.5 pr-3 text-gray-400 text-xs whitespace-nowrap">{new Date(f.created_at).toLocaleString('es-MX')}</td>
                      <td className="py-2.5 pr-3">
                        {f.rating === 'positive' ? (
                          <svg className="w-4 h-4 text-green-400" fill="currentColor" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                            <path d="M15 5.88 14 10h5.83a2 2 0 011.92 2.56l-2.33 8A2 2 0 0117.5 22H4a2 2 0 01-2-2v-8a2 2 0 012-2h2.76a2 2 0 001.79-1.11L12 2a3.13 3.13 0 011 3.88Z" />
                            <path d="M7 10v12" />
                          </svg>
                        ) : (
                          <svg className="w-4 h-4 text-red-400" fill="currentColor" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
                            <path d="M9 18.12 10 14H4.17a2 2 0 01-1.92-2.56l2.33-8A2 2 0 016.5 2H20a2 2 0 012 2v8a2 2 0 01-2 2h-2.76a2 2 0 00-1.79 1.11L12 22a3.13 3.13 0 01-3-3.88Z" />
                            <path d="M17 14V2" />
                          </svg>
                        )}
                      </td>
                      <td className="py-2.5 pr-3 text-gray-300 text-xs">{f.model_name || '—'}</td>
                      <td className="py-2.5 pr-3 text-gray-300 text-xs truncate max-w-[140px]">{f.user_email || '—'}</td>
                      <td className="py-2.5 text-gray-400 text-xs truncate max-w-[220px]" title={f.query_title || undefined}>{f.query_title || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="flex items-center justify-between mt-3 pt-2 border-t border-white/10">
                <span className="text-gray-500 text-xs">Página {feedbackPage} · {feedbackTotal} total</span>
                <div className="flex gap-1">
                  <button
                    onClick={() => setFeedbackPage((p) => Math.max(1, p - 1))}
                    disabled={feedbackPage <= 1}
                    className="px-2 py-1 text-xs rounded bg-white/5 text-gray-400 hover:text-white disabled:opacity-40"
                  >
                    Anterior
                  </button>
                  <button
                    onClick={() => setFeedbackPage((p) => p + 1)}
                    disabled={feedbackData.length < 50 || feedbackPage * 50 >= feedbackTotal}
                    className="px-2 py-1 text-xs rounded bg-white/5 text-gray-400 hover:text-white disabled:opacity-40"
                  >
                    Siguiente
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <p className="text-gray-500 text-sm">{feedbackLoading ? 'Cargando...' : 'No hay comentarios aún.'}</p>
          )}
        </Section>

        {/* Feedback detail modal */}
        {feedbackModalItem && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setFeedbackModalItem(null)}>
            <div className="bg-[#0f172a] border border-white/10 rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between px-5 py-3 border-b border-white/10 bg-white/5">
                <h3 className="text-white font-semibold">Detalle del comentario</h3>
                <button onClick={() => setFeedbackModalItem(null)} className="p-1 text-gray-400 hover:text-white rounded">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-5 space-y-4 custom-scrollbar">
                {/* Feedback details */}
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div><span className="text-gray-500">Fecha</span><p className="text-white">{new Date(feedbackModalItem.created_at).toLocaleString('es-MX')}</p></div>
                  <div><span className="text-gray-500">Usuario</span><p className="text-white">{feedbackModalItem.user_email || '—'}</p></div>
                  <div><span className="text-gray-500">Modelo</span><p className="text-white">{feedbackModalItem.model_name || '—'}</p></div>
                  <div><span className="text-gray-500">Valoración</span>
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full ${feedbackModalItem.rating === 'positive' ? 'bg-green-500/20 text-green-300' : 'bg-red-500/20 text-red-300'}`}>
                      {feedbackModalItem.rating === 'positive' ? 'Positivo' : 'Negativo'}
                    </span>
                  </div>
                  <div className="col-span-2"><span className="text-gray-500">Título / Consulta</span><p className="text-white break-words">{feedbackModalItem.query_title || '—'}</p></div>
                  {feedbackModalItem.reason_category && (
                    <div className="col-span-2"><span className="text-gray-500">Categoría</span><p className="text-white">{REASON_LABELS[feedbackModalItem.reason_category] || feedbackModalItem.reason_category}</p></div>
                  )}
                  {feedbackModalItem.reason_text && (
                    <div className="col-span-2"><span className="text-gray-500">Detalles del usuario</span><p className="text-white whitespace-pre-wrap break-words">{feedbackModalItem.reason_text}</p></div>
                  )}
                  <div className="col-span-2"><span className="text-gray-500">Vista previa de la respuesta</span><p className="text-gray-300 text-xs leading-relaxed whitespace-pre-wrap break-words mt-1">{feedbackModalItem.content_preview || '—'}</p></div>
                  {feedbackModalItem.sources && feedbackModalItem.sources.length > 0 && (
                    <div className="col-span-2">
                      <span className="text-gray-500">Fuentes utilizadas ({feedbackModalItem.sources.length})</span>
                      <ul className="mt-2 space-y-2">
                        {feedbackModalItem.sources.map((s, i) => (
                          <li key={i} className="bg-white/5 rounded-lg px-3 py-2 text-xs">
                            <span className="text-cyan-400 font-medium">
                              {s.type === 'pubmed' ? 'PubMed' : s.type === 'rag' ? 'Ominis' : s.type === 'web' ? 'Web' : 'Fuente'}
                            </span>
                            {s.title && <p className="text-white mt-0.5 truncate" title={s.title}>{s.title}</p>}
                            {s.url && (
                              <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-cyan-400/80 hover:text-cyan-300 truncate block mt-0.5">
                                {s.url}
                              </a>
                            )}
                            {(s.authors || s.year || s.journal) && (
                              <p className="text-gray-500 mt-0.5">{[s.authors, s.year, s.journal].filter(Boolean).join(' · ')}</p>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                {/* Current infrastructure (at time of view) */}
                <div className="pt-4 border-t border-white/10">
                  <h4 className="text-gray-400 text-xs uppercase tracking-wider mb-3">Infraestructura actual (referencia)</h4>
                  <div className="space-y-3 text-sm">
                    {feedbackModalInfra?.health && (
                      <div className="bg-white/5 rounded-lg p-3">
                        <p className="text-gray-500 text-xs mb-1">Estado del sistema</p>
                        <p className="text-white">Estado: {feedbackModalInfra.health.status}</p>
                        <p className="text-gray-400 text-xs">Modelo: {feedbackModalInfra.health.model?.version || '—'} · {feedbackModalInfra.health.model?.status || '—'}</p>
                      </div>
                    )}
                    {feedbackModalInfra?.gpuPerf && (
                      <div className="bg-white/5 rounded-lg p-3">
                        <p className="text-gray-500 text-xs mb-1">Servidor GPU / LLM</p>
                        <p className="text-white">Estado: {feedbackModalInfra.gpuPerf.status}</p>
                        {feedbackModalInfra.gpuPerf.runningModels && feedbackModalInfra.gpuPerf.runningModels.length > 0 && (
                          <p className="text-gray-400 text-xs">Modelos en VRAM: {feedbackModalInfra.gpuPerf.runningModels.map(m => `${m.name} (${m.sizeVramGB}GB)`).join(', ')}</p>
                        )}
                        {feedbackModalInfra.gpuPerf.models && (
                          <p className="text-gray-400 text-xs mt-1">Instalados: {feedbackModalInfra.gpuPerf.models.map(m => m.name).join(', ')}</p>
                        )}
                      </div>
                    )}
                    {feedbackModalInfra?.serverPerf && (
                      <div className="bg-white/5 rounded-lg p-3">
                        <p className="text-gray-500 text-xs mb-1">Servidor de aplicación</p>
                        <p className="text-gray-400 text-xs">
                          {feedbackModalInfra.serverPerf.awsInstanceType && <>{feedbackModalInfra.serverPerf.awsInstanceType}</>}
                          {feedbackModalInfra.serverPerf.awsInstanceId && <> · {feedbackModalInfra.serverPerf.awsInstanceId}</>}
                          {feedbackModalInfra.serverPerf.uptimeHours != null && <> · Uptime: {feedbackModalInfra.serverPerf.uptimeHours}h</>}
                        </p>
                      </div>
                    )}
                    {!feedbackModalInfra && <p className="text-gray-500 text-xs">Cargando infraestructura...</p>}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
