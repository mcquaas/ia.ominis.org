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
  getHealthDatastoreStatus,
  getServerPerformance,
  getGpuServerPerformance,
  getResearchInstanceStatus,
  startResearchInstance,
  stopResearchInstance,
  getLlmInstanceStatus,
  startLlmInstance,
  stopLlmInstance,
  getLlmServersStatus,
  getChatDefaults,
  updateChatDefaults,
  getSiteConfig,
  updateSiteConfig,
  getServersStatus,
  getLLMModelsConfig,
  updateLLMModelConfig,
} from '@/services/auth';
import type { InstanceDetails, ServerWithModels, LLMModelConfigItem } from '@/services/auth';
import { listFeedback, REASON_CATEGORIES } from '@/services/feedback';
import type { FeedbackOut } from '@/services/feedback';

const REASON_LABELS: Record<string, string> = Object.fromEntries(REASON_CATEGORIES.map((c) => [c.value, c.label]));

function InstanceDetailsBlock({ d }: { d: InstanceDetails | undefined }) {
  if (!d) return null;
  const hasInstance = d.instanceId || d.publicIp || d.instanceType;
  if (!hasInstance && !d.modelBase) return null;
  return (
    <div className="text-[10px] text-gray-400 space-y-0.5 mt-2 pt-2 border-t border-white/10">
      {d.modelBase && <div><span className="text-gray-500">Modelo:</span> {d.modelBase}{d.modelDescription ? ` — ${d.modelDescription}` : ''}</div>}
      {d.instanceId && <div><span className="text-gray-500">EC2:</span> {d.instanceId}</div>}
      {d.instanceType && <div><span className="text-gray-500">Tipo:</span> {d.instanceType}</div>}
      {d.publicIp && <div><span className="text-gray-500">IP:</span> {d.publicIp}</div>}
      {(d.vramGb != null || d.ramGb != null) && (
        <div>
          <span className="text-gray-500">Memoria:</span>{' '}
          {d.vramGb != null && `${d.vramGb} GB VRAM`}
          {d.vramGb != null && d.ramGb != null && ' · '}
          {d.ramGb != null && `${d.ramGb} GB RAM`}
        </div>
      )}
    </div>
  );
}

function formatFeedbackDate(createdAt: string | undefined): string {
  if (!createdAt) return '—';
  const d = new Date(createdAt);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('es-MX');
}

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
  const label = s === 'error' ? 'error AWS (permisos EC2)' : s === 'remote' ? 'API remota' : status;
  const cls =
    s === 'remote'
      ? 'bg-gray-500/20 text-gray-300 border-gray-500/30'
      : s === 'online' || s === 'healthy' || s === 'active' || s === 'running' || s === 'stopped'
        ? s === 'running' ? 'bg-green-500/20 text-green-300 border-green-500/30' : 'bg-amber-500/20 text-amber-300 border-amber-500/30'
        : s === 'degraded' || s === 'pending' || s === 'indexing' || s === 'stopping'
          ? 'bg-amber-500/20 text-amber-300 border-amber-500/30'
          : 'bg-red-500/20 text-red-300 border-red-500/30';
  const dotCls = s === 'remote' ? 'bg-gray-400' : s === 'online' || s === 'healthy' || s === 'active' || s === 'running' ? 'bg-green-400' : s === 'degraded' || s === 'pending' || s === 'indexing' || s === 'stopping' || s === 'stopped' ? 'bg-amber-400' : 'bg-red-400';
  return <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full border ${cls}`}>
    <span className={`w-1.5 h-1.5 rounded-full ${dotCls}`} />
    {label}
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

// ---------- LLM model config card (expandable form) ----------
function LLMModelConfigCard({
  model,
  expanded,
  onToggle,
  saving,
  onSave,
}: {
  model: LLMModelConfigItem;
  expanded: boolean;
  onToggle: () => void;
  saving: boolean;
  onSave: (body: Parameters<typeof updateLLMModelConfig>[1]) => Promise<void>;
}) {
  const [displayName, setDisplayName] = useState(model.display_name);
  const [versionLabel, setVersionLabel] = useState(model.version_label);
  const [description, setDescription] = useState(model.description);
  const [backendModel, setBackendModel] = useState(model.backend_model);
  const [backendUrlOverride, setBackendUrlOverride] = useState(model.backend_url_override ?? '');
  const [systemPrompt, setSystemPrompt] = useState(model.system_prompt ?? '');
  const [temperature, setTemperature] = useState(String(model.temperature ?? ''));
  const [numPredict, setNumPredict] = useState(String(model.num_predict ?? ''));
  const [extraParamsJson, setExtraParamsJson] = useState(() => JSON.stringify(model.extra_params ?? {}, null, 2));
  const [isDefault, setIsDefault] = useState(model.is_default);
  const [availableForResearcher, setAvailableForResearcher] = useState(model.available_for_researcher !== false);
  // Sync from model when it changes (e.g. after save)
  useEffect(() => {
    setDisplayName(model.display_name);
    setVersionLabel(model.version_label);
    setDescription(model.description);
    setBackendModel(model.backend_model);
    setBackendUrlOverride(model.backend_url_override ?? '');
    setSystemPrompt(model.system_prompt ?? '');
    setTemperature(String(model.temperature ?? ''));
    setNumPredict(String(model.num_predict ?? ''));
    setExtraParamsJson(JSON.stringify(model.extra_params ?? {}, null, 2));
    setIsDefault(model.is_default);
    setAvailableForResearcher(model.available_for_researcher !== false);
  }, [model.model_id, model.display_name, model.version_label, model.description, model.backend_model, model.backend_url_override, model.system_prompt, model.temperature, model.num_predict, model.extra_params, model.is_default, model.available_for_researcher]);
  const handleSave = () => {
    const body: Parameters<typeof updateLLMModelConfig>[1] = {
      display_name: displayName,
      version_label: versionLabel || undefined,
      description: description || undefined,
      backend_model: backendModel || undefined,
      backend_url_override: backendUrlOverride.trim() || undefined,
      system_prompt: systemPrompt.trim() || undefined,
      temperature: temperature === '' ? undefined : parseFloat(temperature),
      num_predict: numPredict === '' ? undefined : parseInt(numPredict, 10),
      is_default: isDefault,
      available_for_researcher: availableForResearcher,
    };
    try {
      const extra = JSON.parse(extraParamsJson || '{}') as Record<string, unknown>;
      if (extra && typeof extra === 'object' && Object.keys(extra).length) body.extra_params = extra;
    } catch {
      body.extra_params = undefined;
    }
    onSave(body);
  };
  return (
    <div className="bg-white/5 border border-white/10 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-white/5"
      >
        <span className="font-medium text-white">
          {model.display_name}
          {model.version_label && <span className="text-gray-400 ml-2">({model.version_label})</span>}
        </span>
        <span className="text-gray-400 text-xs">{model.model_id}</span>
        <span className="text-gray-500">{expanded ? '▼' : '▶'}</span>
      </button>
      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-white/10 pt-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-[10px] text-gray-500 uppercase mb-1">Nombre para mostrar</label>
              <input type="text" value={displayName} onChange={(e) => setDisplayName(e.target.value)} className="w-full px-2 py-1.5 bg-black/30 border border-white/20 rounded text-sm text-white" />
            </div>
            <div>
              <label className="block text-[10px] text-gray-500 uppercase mb-1">Versión</label>
              <input type="text" value={versionLabel} onChange={(e) => setVersionLabel(e.target.value)} placeholder="ej. 2.0.1" className="w-full px-2 py-1.5 bg-black/30 border border-white/20 rounded text-sm text-white" />
            </div>
          </div>
          <div>
            <label className="block text-[10px] text-gray-500 uppercase mb-1">Descripción</label>
            <input type="text" value={description} onChange={(e) => setDescription(e.target.value)} className="w-full px-2 py-1.5 bg-black/30 border border-white/20 rounded text-sm text-white" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-[10px] text-gray-500 uppercase mb-1">Backend ({model.backend_type}) — modelo</label>
              <input type="text" value={backendModel} onChange={(e) => setBackendModel(e.target.value)} placeholder="ej. qwen2.5:14b" className="w-full px-2 py-1.5 bg-black/30 border border-white/20 rounded text-sm text-white" />
            </div>
            <div>
              <label className="block text-[10px] text-gray-500 uppercase mb-1">URL override (opcional)</label>
              <input type="text" value={backendUrlOverride} onChange={(e) => setBackendUrlOverride(e.target.value)} placeholder="http://host:11434" className="w-full px-2 py-1.5 bg-black/30 border border-white/20 rounded text-sm text-white" />
            </div>
          </div>
          <div>
            <label className="block text-[10px] text-gray-500 uppercase mb-1">System prompt (vacío = por defecto)</label>
            <textarea value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} rows={6} className="w-full px-2 py-1.5 bg-black/30 border border-white/20 rounded text-sm text-white font-mono" placeholder="Eres OMINIS..." />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <label className="block text-[10px] text-gray-500 uppercase mb-1">Temperature</label>
              <input type="text" value={temperature} onChange={(e) => setTemperature(e.target.value)} placeholder="0.3" className="w-full px-2 py-1.5 bg-black/30 border border-white/20 rounded text-sm text-white" />
            </div>
            <div>
              <label className="block text-[10px] text-gray-500 uppercase mb-1">Max tokens</label>
              <input type="text" value={numPredict} onChange={(e) => setNumPredict(e.target.value)} placeholder="2048" className="w-full px-2 py-1.5 bg-black/30 border border-white/20 rounded text-sm text-white" />
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} className="rounded border-white/30" />
                <span className="text-xs text-gray-300">Por defecto</span>
              </label>
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 cursor-pointer" title="Si está desmarcado, solo admin/SuperAdmin podrán usar este modelo; investigadores verán mensaje para solicitar acceso.">
                <input type="checkbox" checked={availableForResearcher} onChange={(e) => setAvailableForResearcher(e.target.checked)} className="rounded border-white/30" />
                <span className="text-xs text-gray-300">Disponible para investigadores</span>
              </label>
            </div>
          </div>
          <div>
            <label className="block text-[10px] text-gray-500 uppercase mb-1">Extra params (JSON, ej. {`{"num_gpu": -1}`})</label>
            <textarea value={extraParamsJson} onChange={(e) => setExtraParamsJson(e.target.value)} rows={2} className="w-full px-2 py-1.5 bg-black/30 border border-white/20 rounded text-sm text-white font-mono" />
          </div>
          <button type="button" onClick={handleSave} disabled={saving} className="px-4 py-2 bg-cyan-500/30 text-cyan-200 rounded text-sm hover:bg-cyan-500/40 disabled:opacity-50">
            {saving ? 'Guardando…' : 'Guardar'}
          </button>
        </div>
      )}
    </div>
  );
}

// ---------- capsule On/Off switch for research instance ----------
function ResearchInstanceSwitch({
  status,
  loading,
  onToggle,
  labelOff = 'Off',
  labelOn = 'On',
}: {
  status: string | null;
  loading: boolean;
  onToggle: () => void;
  labelOff?: string;
  labelOn?: string;
}) {
  const isOn = status === 'running' || status === 'pending';
  const isOff = status === 'stopped' || status === 'stopping' || status === null || status === 'error';
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={loading}
      className="inline-flex rounded-full border border-white/20 bg-white/5 p-0.5 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 disabled:opacity-50"
      aria-pressed={isOn}
    >
      <span
        className={`rounded-full px-3 py-1 text-xs font-medium transition-all ${
          isOff ? 'bg-cyan-500/30 text-cyan-300' : 'text-gray-500'
        }`}
      >
        {loading && !isOn ? '…' : labelOff}
      </span>
      <span
        className={`rounded-full px-3 py-1 text-xs font-medium transition-all ${
          isOn ? 'bg-green-500/30 text-green-300' : 'text-gray-500'
        }`}
      >
        {loading && isOn ? '…' : labelOn}
      </span>
    </button>
  );
}

// =================================================================
export default function DashboardPage() {
  const { user, loading: authLoading, isAdmin, isSuperAdmin } = useAuth();

  const [stats, setStats] = useState<SystemStats | null>(null);
  const [health, setHealth] = useState<{ status: string; model: { version: string; status: string }; servers: Record<string, string> } | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [storeStats, setStoreStats] = useState<{ totalDocuments: number; embeddingModel: string; storageType: string } | null>(null);
  const [healthDatastoreStatus, setHealthDatastoreStatus] = useState<{
    enabled: boolean;
    health_docs: number;
    health_chunks: number;
    evidence_pack_test_count: number;
    opensearch_url_set?: boolean;
    error?: string;
  } | null>(null);
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
  const [actionError, setActionError] = useState('');
  const [researchInstances, setResearchInstances] = useState<{ openscholar: string | null; openscholar_128k: string | null }>({ openscholar: null, openscholar_128k: null });
  const [researchInstanceAction, setResearchInstanceAction] = useState<'openscholar' | 'openscholar_128k' | null>(null);
  const [llmInstances, setLlmInstances] = useState<{ 'ominis-2.0': string | null; 'ominis-2.0-med'?: string | null }>({ 'ominis-2.0': null, 'ominis-2.0-med': null });
  const [llmInstanceDetails, setLlmInstanceDetails] = useState<Record<string, InstanceDetails | undefined>>({ 'ominis-2.0': undefined, 'ominis-2.0-med': undefined });
  const [llmInstanceAction, setLlmInstanceAction] = useState<'ominis-2.0' | 'ominis-2.0-med' | null>(null);
  const [researchInstanceDetails, setResearchInstanceDetails] = useState<Record<'openscholar' | 'openscholar_128k', InstanceDetails | undefined>>({ openscholar: undefined, openscholar_128k: undefined });
  const [serversStatus, setServersStatus] = useState<ServerWithModels[]>([]);
  const [serverActionKey, setServerActionKey] = useState<string | null>(null);
  const [chatDefaults, setChatDefaults] = useState<{ research_mode: boolean; rag_search: boolean; web_search: boolean; pubmed_search: boolean; openscholar_search: boolean; research_2_1: boolean } | null>(null);
  const [chatDefaultsSaving, setChatDefaultsSaving] = useState(false);
  const [llmServersStatus, setLlmServersStatus] = useState<{
    servers: Array<{ label: string; url: string | null; reachable: boolean; models: string[]; note?: string; error?: string }>;
  } | null>(null);
  const [llmModelsConfig, setLlmModelsConfig] = useState<LLMModelConfigItem[]>([]);
  const [llmConfigExpandedId, setLlmConfigExpandedId] = useState<string | null>(null);
  const [llmConfigSavingId, setLlmConfigSavingId] = useState<string | null>(null);

  type DashboardTab = 'overview' | 'servers' | 'llms' | 'rag' | 'users' | 'options';
  const [activeTab, setActiveTab] = useState<DashboardTab>('overview');

  // Site config (banner) — superadmin only
  const [bannerMessage, setBannerMessage] = useState<string>('');
  const [bannerSaving, setBannerSaving] = useState(false);

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
      const [healthRes, statsRes, storeRes, storeHealthRes, perfRes, gpuRes] = await Promise.allSettled([
        getHealth(),
        getSystemStats(),
        getStoreStats(),
        getHealthDatastoreStatus(),
        getServerPerformance(),
        getGpuServerPerformance(),
      ]);

      if (healthRes.status === 'fulfilled') setHealth(healthRes.value as typeof health);
      if (statsRes.status === 'fulfilled') setStats((statsRes.value as { data: SystemStats }).data);
      if (storeRes.status === 'fulfilled') setStoreStats(storeRes.value as typeof storeStats);
      if (storeHealthRes.status === 'fulfilled') setHealthDatastoreStatus(storeHealthRes.value as typeof healthDatastoreStatus);
      if (perfRes.status === 'fulfilled') setServerPerf(perfRes.value as typeof serverPerf);
      if (gpuRes.status === 'fulfilled') setGpuPerf(gpuRes.value as typeof gpuPerf);

      if (isAdmin) {
        try {
          const [ri, li, cd, lss, serversRes, llmConfigRes] = await Promise.all([
            getResearchInstanceStatus(),
            getLlmInstanceStatus(),
            getChatDefaults(),
            getLlmServersStatus(),
            getServersStatus().catch(() => ({ servers: [] })),
            getLLMModelsConfig().catch(() => []),
          ]);
          setResearchInstances({ openscholar: ri.openscholar, openscholar_128k: ri.openscholar_128k });
          setResearchInstanceDetails(ri.details ?? { openscholar: undefined, openscholar_128k: undefined });
          setLlmInstances({ 'ominis-2.0': li['ominis-2.0'], 'ominis-2.0-med': li['ominis-2.0-med'] ?? null });
          setLlmInstanceDetails(li.details ?? { 'ominis-2.0': undefined, 'ominis-2.0-med': undefined });
          setChatDefaults(cd);
          setLlmServersStatus(lss);
          setServersStatus(serversRes?.servers ?? []);
          setLlmModelsConfig(Array.isArray(llmConfigRes) ? llmConfigRes : []);
        } catch { /* non-critical */ }
      }

      if (isSuperAdmin) {
        try {
          const [u, siteConfig] = await Promise.all([getUsers(), getSiteConfig()]);
          setUsers(Array.isArray(u) ? u : []);
          setBannerMessage(siteConfig.banner_message ?? '');
        } catch { /* non-critical */ }
      }

    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error loading data');
    } finally {
      setLoadingData(false);
    }
  }, [isSuperAdmin, isAdmin]);

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
  const showMsg = (msg: string) => { setActionError(''); setActionMsg(msg); setTimeout(() => setActionMsg(''), 4000); };
  const showError = (msg: string) => { setActionMsg(''); setActionError(msg); setTimeout(() => setActionError(''), 6000); };

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

  const handleResearchInstanceStart = async (key: 'openscholar' | 'openscholar_128k') => {
    setResearchInstanceAction(key);
    try {
      await startResearchInstance(key);
      showMsg(key === 'openscholar_128k' ? 'Iniciando modelo 128K. Se apagará en 60 min.' : 'Iniciando OpenScholar (ominis-2.0-research).');
      const ri = await getResearchInstanceStatus();
      setResearchInstances({ openscholar: ri.openscholar, openscholar_128k: ri.openscholar_128k });
      setResearchInstanceDetails(ri.details ?? { openscholar: undefined, openscholar_128k: undefined });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      showError(msg || 'Error al iniciar');
      console.error('Research instance start failed:', e);
    } finally {
      setResearchInstanceAction(null);
    }
  };

  const handleResearchInstanceStop = async (key: 'openscholar' | 'openscholar_128k') => {
    setResearchInstanceAction(key);
    try {
      await stopResearchInstance(key);
      showMsg('Apagando instancia.');
      const ri = await getResearchInstanceStatus();
      setResearchInstances({ openscholar: ri.openscholar, openscholar_128k: ri.openscholar_128k });
      setResearchInstanceDetails(ri.details ?? { openscholar: undefined, openscholar_128k: undefined });
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Error al apagar');
    } finally {
      setResearchInstanceAction(null);
    }
  };

  const handleLlmInstanceStart = async (key: 'ominis-2.0' | 'ominis-2.0-med') => {
    setLlmInstanceAction(key);
    try {
      await startLlmInstance(key);
      showMsg(key === 'ominis-2.0-med' ? 'Iniciando Ominis 2.0 Med.' : 'Iniciando servidor Ominis 2.0 (Qwen).');
      const li = await getLlmInstanceStatus();
      setLlmInstances({ 'ominis-2.0': li['ominis-2.0'], 'ominis-2.0-med': li['ominis-2.0-med'] ?? null });
      setLlmInstanceDetails(li.details ?? { 'ominis-2.0': undefined, 'ominis-2.0-med': undefined });
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Error al iniciar');
    } finally {
      setLlmInstanceAction(null);
    }
  };

  const handleLlmInstanceStop = async (key: 'ominis-2.0' | 'ominis-2.0-med') => {
    setLlmInstanceAction(key);
    try {
      await stopLlmInstance(key);
      showMsg('Apagando servidor LLM.');
      const li = await getLlmInstanceStatus();
      setLlmInstances({ 'ominis-2.0': li['ominis-2.0'], 'ominis-2.0-med': li['ominis-2.0-med'] ?? null });
      setLlmInstanceDetails(li.details ?? { 'ominis-2.0': undefined, 'ominis-2.0-med': undefined });
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Error al apagar');
    } finally {
      setLlmInstanceAction(null);
    }
  };

  const handleServerToggle = async (server: ServerWithModels) => {
    const key = server.primaryKey;
    const isRunning = server.state === 'running' || server.state === 'pending';
    setServerActionKey(key);
    try {
      if (server.primaryKeyType === 'llm') {
        if (isRunning) {
          await stopLlmInstance(key as 'ominis-2.0' | 'ominis-2.0-med');
          showMsg('Apagando servidor.');
        } else {
          await startLlmInstance(key as 'ominis-2.0' | 'ominis-2.0-med');
          showMsg('Iniciando servidor.');
        }
      } else {
        if (isRunning) {
          await stopResearchInstance(key as 'openscholar' | 'openscholar_128k');
          showMsg('Apagando servidor.');
        } else {
          await startResearchInstance(key as 'openscholar' | 'openscholar_128k');
          showMsg('Iniciando servidor.');
        }
      }
      const res = await getServersStatus();
      setServersStatus(res.servers ?? []);
      const [li, ri] = await Promise.all([getLlmInstanceStatus(), getResearchInstanceStatus()]);
      setLlmInstances({ 'ominis-2.0': li['ominis-2.0'], 'ominis-2.0-med': li['ominis-2.0-med'] ?? null });
      setLlmInstanceDetails(li.details ?? { 'ominis-2.0': undefined, 'ominis-2.0-med': undefined });
      setResearchInstances({ openscholar: ri.openscholar, openscholar_128k: ri.openscholar_128k });
      setResearchInstanceDetails(ri.details ?? { openscholar: undefined, openscholar_128k: undefined });
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Error');
    } finally {
      setServerActionKey(null);
    }
  };

  const handleChatDefaultToggle = async (key: 'research_mode' | 'rag_search' | 'web_search' | 'pubmed_search' | 'openscholar_search' | 'research_2_1') => {
    if (!chatDefaults) return;
    const next = !chatDefaults[key];
    setChatDefaults((prev) => (prev ? { ...prev, [key]: next } : prev));
    setChatDefaultsSaving(true);
    try {
      const updated = await updateChatDefaults({ [key]: next });
      setChatDefaults(updated);
      showMsg('Opciones por defecto guardadas.');
    } catch (e) {
      setChatDefaults(chatDefaults);
      showError(e instanceof Error ? e.message : 'Error al guardar');
    } finally {
      setChatDefaultsSaving(false);
    }
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

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-[calc(5rem+var(--banner-height,0px))] pb-12">
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
        {actionError && <div className="mb-4 p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-300 text-sm">{actionError}</div>}
        {actionMsg && <div className="mb-4 p-3 bg-green-500/20 border border-green-500/30 rounded-lg text-green-300 text-sm">{actionMsg}</div>}

        {/* Tabs */}
        <nav className="flex flex-wrap gap-1 mb-6 border-b border-white/10 pb-2">
          {([
            { id: 'overview' as const, label: 'Visión general' },
            { id: 'servers' as const, label: 'Servidores' },
            { id: 'llms' as const, label: 'LLMs' },
            { id: 'rag' as const, label: 'RAG' },
            { id: 'users' as const, label: 'Usuarios' },
            { id: 'options' as const, label: 'Opciones' },
          ]).map(({ id, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => setActiveTab(id)}
              className={`px-4 py-2 rounded-t-lg text-sm font-medium transition-colors ${
                activeTab === id
                  ? 'bg-white/10 text-cyan-300 border border-b-0 border-white/20 -mb-px'
                  : 'text-gray-400 hover:text-white hover:bg-white/5'
              }`}
            >
              {label}
            </button>
          ))}
        </nav>

        {/* ===== Visión general ===== */}
        {activeTab === 'overview' && (
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
        )}

        {/* ===== Servidores ===== */}
        {activeTab === 'servers' && (
        <>
        {/* Server Performance ===== */}
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
        {/* GPU Server Performance */}
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
                {gpuPerf.inference && !gpuPerf.inference.error && (
                  <div className="bg-white/5 rounded-xl p-3">
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Carga del modelo</p>
                    <p className="text-lg font-bold text-green-400">{gpuPerf.inference.loadDurationMs} <span className="text-xs font-normal text-gray-500">ms</span></p>
                    <p className="text-[10px] text-gray-500">Eval: {gpuPerf.inference.evalDurationMs}ms</p>
                  </div>
                )}
                <div className="bg-white/5 rounded-xl p-3">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Modelos activos</p>
                  <p className="text-lg font-bold text-amber-400">{gpuPerf.runningModels?.length || 0}</p>
                  {gpuPerf.runningModels && gpuPerf.runningModels.length > 0 ? (
                    <p className="text-[10px] text-gray-500">{gpuPerf.runningModels.map(m => `${m.name} (${m.sizeVramGB}GB)`).join(', ')}</p>
                  ) : (
                    <p className="text-[10px] text-gray-500">Ninguno en VRAM</p>
                  )}
                </div>
                <div className="bg-white/5 rounded-xl p-3">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Modelos instalados</p>
                  <p className="text-lg font-bold text-purple-400">{gpuPerf.models?.length || 0}</p>
                  <p className="text-[10px] text-gray-500">
                    {gpuPerf.models?.reduce((sum, m) => sum + m.sizeGB, 0).toFixed(1) || 0} GB total
                  </p>
                </div>
              </div>
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
        </>
        )}

        {/* ===== LLMs ===== */}
        {activeTab === 'llms' && (
        <>
        {/* Estado Ollama (URLs y modelos disponibles) ===== */}
        <section className="mb-6">
          <Section title="Estado Ollama">
            {llmServersStatus && llmServersStatus.servers.length > 0 && (
              <div className="mb-4 p-3 bg-white/5 border border-white/10 rounded-lg">
                <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-2">Estado real de cada servidor Ollama (modelos disponibles)</p>
                <ul className="space-y-2 text-sm">
                  {llmServersStatus.servers.map((s) => (
                    <li key={s.label} className="flex flex-wrap items-baseline gap-2">
                      <span className="font-medium text-white">{s.label}</span>
                      {s.url != null ? (
                        <>
                          <span className={`text-xs ${s.reachable ? 'text-green-400' : 'text-red-400'}`}>
                            {s.reachable ? '✓' : '✗'} {s.url.replace(/^https?:\/\//, '')}
                          </span>
                          {s.reachable && s.models.length > 0 && (
                            <span className="text-gray-400 text-xs">→ {s.models.join(', ')}</span>
                          )}
                          {s.error && <span className="text-red-400 text-xs">{s.error}</span>}
                        </>
                      ) : (
                        <span className="text-gray-500 text-xs">{s.note ?? 'no configurado'}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Section>
        </section>

        {/* Servidores GPU (por instancia EC2; un on/off por servidor) ===== */}
        <section className="mb-6">
          <Section title="Servidores GPU">
            <p className="text-[11px] text-gray-500 mb-4">
              Cada tarjeta es una instancia EC2. Prender/apagar afecta todo el servidor (todos los modelos que corren en él).
              Si no hay servidores, configura OLLAMA_INSTANCE_ID, OLLAMA_CLINIC_INSTANCE_ID, OPENSCHOLAR_INSTANCE_ID y/o OPENSCHOLAR_128K_INSTANCE_ID en el backend.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {serversStatus.map((srv) => {
                const isRemote = srv.isRemote || srv.instanceId === 'remote-power';
                return (
                <div key={srv.instanceId} className="bg-white/5 border border-white/10 rounded-xl p-4">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="text-sm font-semibold text-white truncate" title={srv.instanceId}>
                      {isRemote ? 'Ominis 2.0 Power (API remota)' : (srv.publicIp || srv.instanceId)}
                    </h4>
                    <StatusBadge status={isRemote ? 'remote' : srv.state} />
                  </div>
                  <div className="text-[10px] text-gray-400 space-y-0.5 mb-3">
                    {!isRemote && srv.instanceId && <div><span className="text-gray-500">EC2:</span> {srv.instanceId}</div>}
                    {!isRemote && srv.instanceType && <div><span className="text-gray-500">Tipo:</span> {srv.instanceType}</div>}
                    {(srv.vramGb != null || srv.ramGb != null) && (
                      <div>
                        <span className="text-gray-500">Memoria:</span>{' '}
                        {srv.vramGb != null && `${srv.vramGb} GB VRAM`}
                        {srv.vramGb != null && srv.ramGb != null && ' · '}
                        {srv.ramGb != null && `${srv.ramGb} GB RAM`}
                      </div>
                    )}
                    {srv.estimatedMonthlyUsd != null && (
                      <div><span className="text-gray-500">Costo est.:</span> ~${srv.estimatedMonthlyUsd}/mes (on-demand)</div>
                    )}
                  </div>
                  <div className="mb-3">
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Modelos en este servidor</p>
                    <ul className="text-[11px] text-gray-300 space-y-0.5">
                      {srv.models.map((m) => (
                        <li key={m.key}>
                          <span className="font-medium text-white">{m.label}</span>
                          {m.modelBase && <span className="text-gray-400"> — {m.modelBase}</span>}
                          {m.modelDescription && <span className="text-gray-500"> ({m.modelDescription})</span>}
                        </li>
                      ))}
                    </ul>
                  </div>
                  {!isRemote && (
                  <div className="flex items-center gap-2">
                    <ResearchInstanceSwitch
                      status={srv.state}
                      loading={serverActionKey === srv.primaryKey}
                      onToggle={() => handleServerToggle(srv)}
                      labelOff="Off"
                      labelOn="On"
                    />
                  </div>
                  )}
                  {isRemote && (
                  <p className="text-[11px] text-gray-500">Sin EC2 asociado. Configura POWER_INSTANCE_ID para encender/apagar desde aquí.</p>
                  )}
                </div>
              ); })}
            </div>
            {serversStatus.length === 0 && !loadingData && (
              <p className="text-[11px] text-amber-400/90">No hay servidores configurados o no se pudo obtener el estado (revisa credenciales AWS en us-east-1).</p>
            )}
          </Section>
        </section>

        {/* Configuración de LLMs (asignaciones, prompts, versión, parámetros) — Admin/Superadmin */}
        <section className="mb-6">
          <Section title="Configuración de LLMs">
            <p className="text-[11px] text-gray-500 mb-4">
              Asignaciones (qué modelo Ominis usa detrás), system prompt, versión y parámetros por modelo. Los cambios se aplican al guardar (sin reiniciar backend).
            </p>
            {llmModelsConfig.length === 0 && !loadingData && (
              <p className="text-[11px] text-gray-500">No hay modelos de chat configurados o no se pudo cargar.</p>
            )}
            <div className="space-y-3">
              {llmModelsConfig.map((m) => (
                <LLMModelConfigCard
                  key={m.model_id}
                  model={m}
                  expanded={llmConfigExpandedId === m.model_id}
                  onToggle={() => setLlmConfigExpandedId((id) => (id === m.model_id ? null : m.model_id))}
                  saving={llmConfigSavingId === m.model_id}
                  onSave={async (body) => {
                    setLlmConfigSavingId(m.model_id);
                    try {
                      await updateLLMModelConfig(m.model_id, body);
                      showMsg('Configuración guardada.');
                      const next = await getLLMModelsConfig();
                      setLlmModelsConfig(next);
                    } catch (e) {
                      showError(e instanceof Error ? e.message : 'Error al guardar');
                    } finally {
                      setLlmConfigSavingId(null);
                    }
                  }}
                />
              ))}
            </div>
          </Section>
        </section>
        </>
        )}

        {/* ===== RAG ===== */}
        {activeTab === 'rag' && (
        <div className="mb-6 space-y-4">
          {storeStats && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <StatCard label="Documentos" value={storeStats.totalDocuments} color="purple" />
              <StatCard label="Modelo de embeddings" value={storeStats.embeddingModel || '—'} color="cyan" />
              <StatCard label="Almacenamiento" value={storeStats.storageType || '—'} color="blue" />
            </div>
          )}
          {healthDatastoreStatus != null && (
            <Section title="Ingesta nocturna (Health Datastore México)">
              {!healthDatastoreStatus.enabled ? (
                <p className="text-gray-400 text-sm">Desactivado. Actívalo en el backend con <code className="text-gray-300">HEALTH_DATASTORE_ENABLED=true</code>.</p>
              ) : healthDatastoreStatus.error ? (
                <p className="text-amber-300 text-sm">Error: {healthDatastoreStatus.error}</p>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <StatCard label="Documentos salud" value={healthDatastoreStatus.health_docs} color="green" />
                  <StatCard label="Chunks indexados" value={healthDatastoreStatus.health_chunks} color="green" />
                  <StatCard label="Prueba retrieval (top 5)" value={healthDatastoreStatus.evidence_pack_test_count} sub="consulta de prueba" color="cyan" />
                </div>
              )}
            </Section>
          )}
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
        )}

        {/* ===== Usuarios ===== */}
        {activeTab === 'users' && (
        <>
        {/* User Management (SuperAdmin only) ===== */}
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
                      <td className="py-2.5 pr-3 text-gray-400 text-xs whitespace-nowrap">{formatFeedbackDate(f.created_at)}</td>
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
        </>
        )}

        {/* ===== Opciones ===== */}
        {activeTab === 'options' && (
        <section className="mb-6">
          <Section title="Opciones por defecto del chat">
            <p className="text-[11px] text-gray-500 mb-4">
              Valores iniciales que verán todos los usuarios al abrir el chat. Cada usuario puede cambiarlos en el menú + durante la conversación.
              {chatDefaultsSaving && <span className="ml-2 text-amber-400">Guardando…</span>}
            </p>
            {chatDefaults && (
              <div className="space-y-3">
                <div className="flex items-center justify-between py-2 border-b border-white/10">
                  <div>
                    <p className="text-sm font-medium text-white">Investigación</p>
                    <p className="text-[10px] text-gray-500">Modo investigación (reporte académico)</p>
                  </div>
                  <ResearchInstanceSwitch
                    status={chatDefaults.research_mode ? 'running' : 'stopped'}
                    loading={chatDefaultsSaving}
                    onToggle={() => handleChatDefaultToggle('research_mode')}
                    labelOff="Off"
                    labelOn="On"
                  />
                </div>
                <div className="flex items-center justify-between py-2 border-b border-white/10">
                  <div>
                    <p className="text-sm font-medium text-white">Research 2.1</p>
                    <p className="text-[10px] text-gray-500">Investigación profunda: segunda ronda de fuentes y reporte sección por sección (requiere OpenScholar 128K)</p>
                  </div>
                  <ResearchInstanceSwitch
                    status={chatDefaults.research_2_1 ? 'running' : 'stopped'}
                    loading={chatDefaultsSaving}
                    onToggle={() => handleChatDefaultToggle('research_2_1')}
                    labelOff="Off"
                    labelOn="On"
                  />
                </div>
                <div className="flex items-center justify-between py-2 border-b border-white/10">
                  <div>
                    <p className="text-sm font-medium text-white">Ominis (base de datos)</p>
                    <p className="text-[10px] text-gray-500">Búsqueda en documentos indexados</p>
                  </div>
                  <ResearchInstanceSwitch
                    status={chatDefaults.rag_search ? 'running' : 'stopped'}
                    loading={chatDefaultsSaving}
                    onToggle={() => handleChatDefaultToggle('rag_search')}
                    labelOff="Off"
                    labelOn="On"
                  />
                </div>
                <div className="flex items-center justify-between py-2 border-b border-white/10">
                  <div>
                    <p className="text-sm font-medium text-white">PubMed</p>
                    <p className="text-[10px] text-gray-500">Búsqueda en literatura médica</p>
                  </div>
                  <ResearchInstanceSwitch
                    status={chatDefaults.pubmed_search ? 'running' : 'stopped'}
                    loading={chatDefaultsSaving}
                    onToggle={() => handleChatDefaultToggle('pubmed_search')}
                    labelOff="Off"
                    labelOn="On"
                  />
                </div>
                <div className="flex items-center justify-between py-2 border-b border-white/10">
                  <div>
                    <p className="text-sm font-medium text-white">Web</p>
                    <p className="text-[10px] text-gray-500">Búsqueda en la web</p>
                  </div>
                  <ResearchInstanceSwitch
                    status={chatDefaults.web_search ? 'running' : 'stopped'}
                    loading={chatDefaultsSaving}
                    onToggle={() => handleChatDefaultToggle('web_search')}
                    labelOff="Off"
                    labelOn="On"
                  />
                </div>
                <div className="flex items-center justify-between py-2">
                  <div>
                    <p className="text-sm font-medium text-white">Open Scholar</p>
                    <p className="text-[10px] text-gray-500">Búsqueda en Semantic Scholar (artículos académicos)</p>
                  </div>
                  <ResearchInstanceSwitch
                    status={chatDefaults.openscholar_search ? 'running' : 'stopped'}
                    loading={chatDefaultsSaving}
                    onToggle={() => handleChatDefaultToggle('openscholar_search')}
                    labelOff="Off"
                    labelOn="On"
                  />
                </div>
              </div>
            )}
            {!chatDefaults && !chatDefaultsSaving && <p className="text-gray-500 text-sm">Cargando…</p>}
          </Section>

          {isSuperAdmin && (
            <Section title="Notificación global (solo Super Admin)">
              <p className="text-[11px] text-gray-500 mb-4">
                Mensaje en amarillo en la parte superior de Ominis para todos los usuarios (ej.: avisos de mantenimiento o incidencias).
              </p>
              <textarea
                value={bannerMessage}
                onChange={(e) => setBannerMessage(e.target.value)}
                placeholder="Ej.: Estamos experimentando problemas con..."
                className="w-full min-h-[80px] px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                maxLength={500}
              />
              <p className="text-[10px] text-gray-500 mt-1">{bannerMessage.length}/500</p>
              <div className="flex gap-2 mt-3">
                <button
                  type="button"
                  onClick={async () => {
                    setBannerSaving(true);
                    try {
                      await updateSiteConfig({ banner_message: bannerMessage.trim() || null });
                      showMsg('Notificación guardada.');
                    } catch {
                      showError('Error al guardar.');
                    } finally {
                      setBannerSaving(false);
                    }
                  }}
                  disabled={bannerSaving}
                  className="px-4 py-2 rounded-lg bg-amber-500/20 text-amber-300 border border-amber-500/30 hover:bg-amber-500/30 text-sm font-medium disabled:opacity-50"
                >
                  {bannerSaving ? 'Guardando…' : 'Guardar'}
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    setBannerSaving(true);
                    try {
                      await updateSiteConfig({ banner_message: null });
                      setBannerMessage('');
                      showMsg('Notificación eliminada.');
                    } catch {
                      showError('Error al eliminar.');
                    } finally {
                      setBannerSaving(false);
                    }
                  }}
                  disabled={bannerSaving}
                  className="px-4 py-2 rounded-lg bg-white/10 text-gray-300 border border-white/10 hover:bg-white/15 text-sm font-medium disabled:opacity-50"
                >
                  Limpiar
                </button>
              </div>
            </Section>
          )}
        </section>
        )}

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
                  <div><span className="text-gray-500">Fecha</span><p className="text-white">{formatFeedbackDate(feedbackModalItem.created_at)}</p></div>
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
                              {s.type === 'pubmed' ? 'PubMed' : s.type === 'rag' ? 'Ominis' : s.type === 'web' ? 'Web' : s.type === 'openscholar' ? 'Open Scholar' : 'Fuente'}
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
