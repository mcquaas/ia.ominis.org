'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '@/hooks/useAuth';
import Header from '@/components/Header';
import Link from 'next/link';
import {
  getRagSources,
  getStoreStats,
  getTaxonomyStats,
  getSourceChunks,
  uploadRagFile,
  createRagSource,
  createRagSourcesBatch,
  deleteRagSource,
  reindexSource,
  classifySource,
  batchReindex,
  markStuckIndexingAsFailed,
  reconcileRagSourceStatus,
  getTaxonomySchema,
  scrapePreview,
  scrapeAndIndex,
  tainacanPreview,
  tainacanImport,
  datosGobMxPreview,
  datosGobMxImport,
  datasetPreview,
  datasetIndex,
} from '@/services/auth';
import type { RagSource, TaxonomyDict } from '@/types/auth';

type TaxonomySchema = Record<string, string[]>;

// ---------- Stat Card ----------
function StatCard({
  label,
  value,
  sub,
  color = 'cyan',
}: {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}) {
  const colorMap: Record<string, string> = {
    cyan: 'from-cyan-500/20 to-cyan-600/5 border-cyan-500/30 text-cyan-300',
    green: 'from-green-500/20 to-green-600/5 border-green-500/30 text-green-300',
    amber: 'from-amber-500/20 to-amber-600/5 border-amber-500/30 text-amber-300',
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

// ---------- Status Badge ----------
function StatusBadge({ status }: { status: string }) {
  const s = status?.toLowerCase();
  const cls =
    s === 'active'
      ? 'bg-green-500/20 text-green-300 border-green-500/30'
      : s === 'indexing' || s === 'pending'
        ? 'bg-amber-500/20 text-amber-300 border-amber-500/30'
        : 'bg-red-500/20 text-red-300 border-red-500/30';
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full border ${cls}`}>
      <span
        className={`w-1.5 h-1.5 rounded-full ${s === 'active' ? 'bg-green-400' : s === 'indexing' || s === 'pending' ? 'bg-amber-400 animate-pulse' : 'bg-red-400'}`}
      />
      {status}
    </span>
  );
}

// ---------- Section ----------
function Section({
  title,
  children,
  action,
}: {
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
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

// ---------- DIMENSION LABELS (human-readable) ----------
const DIM_LABELS: Record<string, string> = {
  institucion: 'Institución',
  tipo_documento: 'Tipo de documento',
  marco_normativo: 'Marco normativo',
  funcion_salud: 'Función salud',
  dominio_salud: 'Dominio salud',
  poblacion_objetivo: 'Población objetivo',
  nivel_atencion: 'Nivel atención',
  territorio: 'Territorio',
  financiamiento: 'Financiamiento',
  tecnologia_insumos: 'Tecnología/insumos',
  datos_digital: 'Datos digital',
  vigencia: 'Vigencia',
};

export default function RagPage() {
  const { user, loading: authLoading, isAdmin, isDeveloper } = useAuth();

  const [storeStats, setStoreStats] = useState<{
    totalDocuments: number;
    embeddingModel: string;
    storageType: string;
  } | null>(null);
  const [taxonomyStats, setTaxonomyStats] = useState<Record<string, Record<string, number>> | null>(null);
  const [sources, setSources] = useState<RagSource[]>([]);
  const [totalSources, setTotalSources] = useState(0);
  const [sourcesPage, setSourcesPage] = useState(1);
  const [pageSize] = useState(25);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [taxonomySchema, setTaxonomySchema] = useState<TaxonomySchema | null>(null);
  const [search, setSearch] = useState('');
  const [taxonomyFilters, setTaxonomyFilters] = useState<TaxonomyDict>({});
  const [error, setError] = useState('');
  const [actionMsg, setActionMsg] = useState('');

  // Upload state
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploadCategory, setUploadCategory] = useState('');
  const [uploadUrl, setUploadUrl] = useState('');
  const [uploadFollowLinks, setUploadFollowLinks] = useState(false);
  const [uploadText, setUploadText] = useState('');
  const [uploadMode, setUploadMode] = useState<
    'file' | 'text' | 'url' | 'scrape' | 'dataset' | 'tainacan' | 'datosgob'
  >('file');
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Scrape state (PDF + CSV + XLS + XLSX)
  const [scrapeUrl, setScrapeUrl] = useState('');
  const [scrapeLoading, setScrapeLoading] = useState(false);
  const [scrapedFiles, setScrapedFiles] = useState<
    Array<{ title: string; fileUrl: string; sourcePage: string; format: string; selected: boolean }>
  >([]);
  const [scrapePreviewDone, setScrapePreviewDone] = useState(false);

  // Dataset state
  const [datasetUrl, setDatasetUrl] = useState('');
  const [datasetLoading, setDatasetLoading] = useState(false);
  const [datasetPreviewData, setDatasetPreviewData] = useState<{
    pageTitle: string;
    pageMetadata: Record<string, string>;
    totalResources: number;
    resources: Array<{
      title: string;
      description: string;
      url: string;
      format: string;
      resourceId: string;
      sourcePage: string;
      selected: boolean;
    }>;
  } | null>(null);

  // Tainacan state
  const [tainacanLoading, setTainacanLoading] = useState(false);
  const [tainacanPreviewData, setTainacanPreviewData] = useState<{
    totalItems: number;
    indexableFiles: number;
    metadataOnly: number;
    byExtension: Record<string, number>;
  } | null>(null);
  const [tainacanImporting, setTainacanImporting] = useState(false);
  const [tainacanResult, setTainacanResult] = useState('');

  const [datosGobLoading, setDatosGobLoading] = useState(false);
  const [datosGobPreviewData, setDatosGobPreviewData] = useState<{
    totalPackages: number;
    groupName: string;
    groupTitle: string;
    totalResourcesSample: number;
    resourceFormatsSample: Record<string, number>;
    sampleTitles: string[];
  } | null>(null);
  const [datosGobImporting, setDatosGobImporting] = useState(false);
  const [datosGobResult, setDatosGobResult] = useState('');

  // Chunk viewer
  const [viewingChunks, setViewingChunks] = useState<number | null>(null);
  const [chunks, setChunks] = useState<Array<{ id: string; contentPreview: string; title?: string; url?: string }>>([]);
  const [chunksLoading, setChunksLoading] = useState(false);
  /** Invalidates in-flight chunk fetches when switching sources or closing the viewer. */
  const chunkFetchSeq = useRef(0);

  const showMsg = (msg: string) => {
    setActionMsg(msg);
    setTimeout(() => setActionMsg(''), 4000);
  };

  const loadStats = useCallback(async () => {
    try {
      const [storeRes, taxRes] = await Promise.allSettled([
        getStoreStats(),
        getTaxonomyStats(),
      ]);
      if (storeRes.status === 'fulfilled') setStoreStats(storeRes.value);
      if (taxRes.status === 'fulfilled') setTaxonomyStats((taxRes.value as { taxonomyStats: Record<string, Record<string, number>> }).taxonomyStats || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error loading stats');
    }
  }, []);

  const loadSources = useCallback(async () => {
    setSourcesLoading(true);
    try {
      const res = await getRagSources({
        page: sourcesPage,
        pageSize,
        search: search.trim() || undefined,
        taxonomy: Object.keys(taxonomyFilters).length > 0 ? taxonomyFilters : undefined,
      });
      setSources(res.data || []);
      setTotalSources(res.meta?.pagination?.total ?? 0);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error loading sources');
    } finally {
      setSourcesLoading(false);
    }
  }, [sourcesPage, pageSize, search, taxonomyFilters]);

  const loadTaxonomySchema = useCallback(async () => {
    try {
      const res = await getTaxonomySchema();
      setTaxonomySchema(res.taxonomy || null);
    } catch {
      /* non-critical */
    }
  }, []);

  useEffect(() => {
    if (isAdmin || isDeveloper) {
      loadStats();
      loadTaxonomySchema();
    }
  }, [isAdmin, isDeveloper, loadStats, loadTaxonomySchema]);

  useEffect(() => {
    if (isAdmin || isDeveloper) loadSources();
  }, [isAdmin, isDeveloper, loadSources]);

  const handleDeleteSource = async (id: number, title: string) => {
    if (!confirm(`Eliminar fuente "${title}" y todos sus chunks? Esta acción es irreversible.`)) return;
    try {
      await deleteRagSource(id);
      showMsg('Fuente eliminada');
      loadSources();
    } catch {
      showMsg('Error al eliminar fuente');
    }
  };

  const handleReindex = async (id: number) => {
    try {
      await reindexSource(id);
      showMsg('Re-indexación iniciada');
      loadSources();
    } catch {
      showMsg('Error al re-indexar');
    }
  };

  const handleClassify = async (id: number) => {
    try {
      await classifySource(id);
      showMsg('Clasificación iniciada');
      loadSources();
    } catch {
      showMsg('Error al clasificar');
    }
  };

  const handleBatchReindex = async () => {
    try {
      const res = await batchReindex({ onlyWithTaxonomy: true });
      showMsg(`${res.totalQueued} fuentes enviadas para re-indexación`);
      loadSources();
    } catch {
      showMsg('Error al re-indexar en lote');
    }
  };

  const [markingStuck, setMarkingStuck] = useState(false);
  const handleMarkStuckAsFailed = async () => {
    setMarkingStuck(true);
    try {
      const res = await markStuckIndexingAsFailed(30);
      if (res.promoted > 0 || res.markedError > 0) {
        const parts: string[] = [];
        if (res.promoted > 0) {
          parts.push(
            `${res.promoted} fuente(s) pasaron a activas (ya había vectores; la indexación había quedado mal registrada)`,
          );
        }
        if (res.markedError > 0) {
          parts.push(`${res.markedError} fuente(s) marcadas como fallidas (sin vectores; puedes re-indexar)`);
        }
        showMsg(parts.join('. ') + '.');
        loadSources();
      } else {
        showMsg('No hay fuentes atascadas en indexación (más de 30 min).');
      }
    } catch {
      showMsg('Error al marcar fuentes atascadas');
    } finally {
      setMarkingStuck(false);
    }
  };

  const [reconciling, setReconciling] = useState(false);
  const handleReconcileStatus = async () => {
    setReconciling(true);
    try {
      const res = await reconcileRagSourceStatus(false, true);
      if (res.fixed > 0 || res.syncedCounts > 0) {
        const parts: string[] = [];
        if (res.fixed > 0) {
          parts.push(`${res.fixed} fuente(s) pasaron de error/indexing a activas`);
        }
        if (res.syncedCounts > 0) {
          parts.push(`${res.syncedCounts} fuente(s) sincronizaron su conteo real de chunks`);
        }
        showMsg(`${parts.join('. ')}. Revisadas: ${res.checked}.`);
        loadSources();
      } else {
        showMsg(
          res.checked > 0
            ? `No hubo cambios al reconciliar ${res.checked} fuente(s).`
            : 'No hay fuentes para reconciliar.',
        );
      }
    } catch {
      showMsg('Error al reconciliar estados');
    } finally {
      setReconciling(false);
    }
  };

  const handleViewChunks = async (sourceId: number) => {
    if (viewingChunks === sourceId) {
      chunkFetchSeq.current += 1;
      setViewingChunks(null);
      setChunks([]);
      return;
    }
    const seq = ++chunkFetchSeq.current;
    setViewingChunks(sourceId);
    setChunks([]);
    setChunksLoading(true);
    try {
      const res = await getSourceChunks(sourceId);
      if (seq !== chunkFetchSeq.current) return;
      setChunks(res.data || []);
    } catch {
      if (seq !== chunkFetchSeq.current) return;
      setChunks([]);
    } finally {
      if (seq === chunkFetchSeq.current) setChunksLoading(false);
    }
  };

  const handleUpload = async () => {
    setUploading(true);
    try {
      if (uploadMode === 'file' && uploadFile) {
        const title = uploadTitle || uploadFile.name.replace(/\.[^.]+$/, '');
        await uploadRagFile(uploadFile, { title, category: uploadCategory });
        showMsg(`Archivo "${uploadFile.name}" subido. Indexando...`);
      } else if (uploadMode === 'text' && uploadText.trim()) {
        const title = uploadTitle || 'Texto manual';
        await createRagSource({ title, content: uploadText, category: uploadCategory, sourceType: 'text' });
        showMsg('Texto indexado correctamente');
      } else if (uploadMode === 'url' && uploadUrl.trim()) {
        const urls = uploadUrl.trim().split(/\n/).map((u) => u.trim()).filter(Boolean);
        if (urls.length === 0) {
          showMsg('Escribe al menos una URL');
          setUploading(false);
          return;
        }
        if (urls.length > 1 || uploadFollowLinks) {
          const res = await createRagSourcesBatch({
            urls,
            crawl: uploadFollowLinks,
            category: uploadCategory,
          });
          showMsg(res.message || `${res.queued} fuentes en cola`);
        } else {
          await createRagSource({
            title: uploadTitle || urls[0],
            sourceUrl: urls[0],
            category: uploadCategory,
            sourceType: 'webpage',
          });
          showMsg('URL enviada para indexación');
        }
      } else {
        showMsg('Proporciona un archivo, texto o URL');
        setUploading(false);
        return;
      }
      setUploadFile(null);
      setUploadTitle('');
      setUploadCategory('');
      setUploadUrl('');
      setUploadText('');
      if (fileInputRef.current) fileInputRef.current.value = '';
      loadSources();
    } catch (e) {
      showMsg(e instanceof Error ? e.message : 'Error al indexar');
    } finally {
      setUploading(false);
    }
  };

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f) {
      setUploadFile(f);
      setUploadMode('file');
    }
  };

  const handleScrapePreview = async () => {
    if (!scrapeUrl.trim()) return;
    setScrapeLoading(true);
    setScrapePreviewDone(false);
    setScrapedFiles([]);
    try {
      const result = await scrapePreview(scrapeUrl);
      const list = (result.files && result.files.length > 0
        ? result.files
        : result.pdfs.map((p) => ({ title: p.title, fileUrl: p.pdfUrl, sourcePage: p.sourcePage, format: 'pdf' }))
      ).map((f) => ({ ...f, selected: true }));
      setScrapedFiles(list);
      setScrapePreviewDone(true);
      if (list.length === 0) showMsg('No se encontraron PDF/CSV/XLS en esta URL');
    } catch (e) {
      showMsg(e instanceof Error ? e.message : 'Error al escanear URL');
    } finally {
      setScrapeLoading(false);
    }
  };

  const handleScrapeIndex = async () => {
    const selected = scrapedFiles.filter((p) => p.selected);
    if (selected.length === 0) {
      showMsg('Selecciona al menos un archivo');
      return;
    }
    setUploading(true);
    try {
      const result = await scrapeAndIndex(scrapeUrl, {
        category: uploadCategory,
        files: selected.map((p) => ({ title: p.title, fileUrl: p.fileUrl, sourcePage: p.sourcePage, format: p.format })),
      });
      showMsg(`${result.totalQueued} archivos enviados para indexación`);
      setScrapeUrl('');
      setScrapedFiles([]);
      setScrapePreviewDone(false);
      setUploadCategory('');
      loadSources();
    } catch (e) {
      showMsg(e instanceof Error ? e.message : 'Error al indexar archivos');
    } finally {
      setUploading(false);
    }
  };

  const toggleAllScrapedFiles = (selected: boolean) => {
    setScrapedFiles((prev) => prev.map((p) => ({ ...p, selected })));
  };

  const handleTainacanPreview = async () => {
    setTainacanLoading(true);
    setTainacanResult('');
    try {
      const result = await tainacanPreview();
      setTainacanPreviewData(result);
    } catch (e) {
      showMsg(e instanceof Error ? e.message : 'Error al conectar con Tainacan');
    } finally {
      setTainacanLoading(false);
    }
  };

  const handleTainacanImport = async () => {
    setTainacanImporting(true);
    setTainacanResult('');
    try {
      const result = await tainacanImport({
        category: uploadCategory || 'tainacan',
        skipExisting: true,
      });
      setTainacanResult(`${result.totalQueued} fuentes enviadas para indexación (${result.skipped} omitidas por ya existir)`);
      showMsg(result.message);
      loadSources();
    } catch (e) {
      setTainacanResult(e instanceof Error ? e.message : 'Error al importar');
      showMsg(e instanceof Error ? e.message : 'Error al importar desde Tainacan');
    } finally {
      setTainacanImporting(false);
    }
  };

  const handleDatosGobPreview = async () => {
    setDatosGobLoading(true);
    setDatosGobResult('');
    try {
      const result = await datosGobMxPreview('salud');
      setDatosGobPreviewData(result);
    } catch (e) {
      showMsg(e instanceof Error ? e.message : 'Error al consultar datos.gob.mx (CKAN)');
    } finally {
      setDatosGobLoading(false);
    }
  };

  const handleDatosGobImport = async () => {
    setDatosGobImporting(true);
    setDatosGobResult('');
    try {
      const result = await datosGobMxImport({
        category: uploadCategory || 'datos.gob.mx',
        skipExisting: true,
        group: 'salud',
      });
      setDatosGobResult(
        `${result.totalQueued} conjuntos encolados para indexación de metadatos (${result.skipped} omitidos por ya existir)`,
      );
      showMsg(result.message);
      loadSources();
    } catch (e) {
      setDatosGobResult(e instanceof Error ? e.message : 'Error al importar');
      showMsg(e instanceof Error ? e.message : 'Error al importar desde datos.gob.mx');
    } finally {
      setDatosGobImporting(false);
    }
  };

  const handleDatasetPreview = async () => {
    if (!datasetUrl.trim()) return;
    setDatasetLoading(true);
    setDatasetPreviewData(null);
    try {
      const result = await datasetPreview(datasetUrl);
      setDatasetPreviewData({
        ...result,
        resources: result.resources.map((r) => ({ ...r, selected: true })),
      });
    } catch (e) {
      showMsg(e instanceof Error ? e.message : 'Error al escanear la página de datasets');
    } finally {
      setDatasetLoading(false);
    }
  };

  const handleDatasetIndex = async () => {
    if (!datasetPreviewData) return;
    const selected = datasetPreviewData.resources.filter((r) => r.selected);
    if (selected.length === 0) return;
    setUploading(true);
    try {
      const result = await datasetIndex(datasetUrl, {
        category: uploadCategory || datasetPreviewData.pageMetadata?.['Tema'] || 'dataset',
        pageTitle: datasetPreviewData.pageTitle,
        pageMetadata: datasetPreviewData.pageMetadata,
        resources: selected.map(({ selected: _, ...r }) => r),
      });
      showMsg(`${result.totalQueued} recursos enviados para indexación`);
      setDatasetUrl('');
      setDatasetPreviewData(null);
      setUploadCategory('');
      loadSources();
    } catch (e) {
      showMsg(e instanceof Error ? e.message : 'Error al indexar datasets');
    } finally {
      setUploading(false);
    }
  };

  const toggleAllDatasetResources = (sel: boolean) => {
    if (datasetPreviewData) {
      setDatasetPreviewData({
        ...datasetPreviewData,
        resources: datasetPreviewData.resources.map((r) => ({ ...r, selected: sel })),
      });
    }
  };

  const setTaxonomyFilter = (dim: string, values: string[]) => {
    setTaxonomyFilters((prev) => {
      const next = { ...prev };
      if (values.length === 0) delete next[dim];
      else next[dim] = values;
      return next;
    });
    setSourcesPage(1);
  };

  if (authLoading) {
    return (
      <div className="min-h-screen bg-[#0a1628] flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-400" />
      </div>
    );
  }

  if (!user || (!isAdmin && !isDeveloper)) {
    return (
      <div className="min-h-screen bg-[#0a1628] flex flex-col">
        <Header />
        <div className="flex-1 flex items-center justify-center pt-16">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-red-400">Acceso Denegado</h1>
            <p className="mt-2 text-gray-400">Necesitas permisos de administrador.</p>
            <Link href="/" className="mt-4 inline-block text-cyan-400 hover:underline">
              Volver al inicio
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a1628]">
      <Header />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-12">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-white">DataStore</h1>
            <p className="text-gray-400 text-sm mt-1">Ingestión, búsqueda y filtrado por taxonomía</p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/dashboard"
              className="flex items-center gap-2 bg-white/10 hover:bg-white/15 text-white text-sm px-4 py-2 rounded-lg border border-white/10 transition-colors"
            >
              Dashboard
            </Link>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}
        {actionMsg && (
          <div className="mb-4 p-3 bg-green-500/20 border border-green-500/30 rounded-lg text-green-300 text-sm">
            {actionMsg}
          </div>
        )}

        {/* Stats */}
        <section className="mb-6">
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
            <StatCard
              label="Documentos"
              value={storeStats?.totalDocuments ?? '—'}
              sub={storeStats?.storageType}
              color="purple"
            />
            {taxonomyStats?.institucion &&
              Object.entries(taxonomyStats.institucion)
                .slice(0, 4)
                .map(([value, cnt]) => (
                  <StatCard key={value} label={value} value={cnt} color="cyan" />
                ))}
            {taxonomyStats?.tipo_documento &&
              Object.entries(taxonomyStats.tipo_documento)
                .slice(0, 4)
                .map(([value, cnt]) => (
                  <StatCard key={value} label={value} value={cnt} color="amber" />
                ))}
          </div>
          <p className="text-gray-400 text-xs mt-3">
            Modelo embedding: {storeStats?.embeddingModel ?? '—'}
          </p>
        </section>

        {/* Ingest */}
        <div className="mb-6">
          <Section title="Agregar fuente">
            <div className="flex gap-2 mb-4">
              {(['file', 'text', 'url', 'scrape', 'dataset', 'tainacan', 'datosgob'] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => {
                    setUploadMode(m);
                    if (m === 'scrape') {
                      setScrapePreviewDone(false);
                      setScrapedFiles([]);
                    }
                    if (m === 'tainacan') {
                      setTainacanPreviewData(null);
                      setTainacanResult('');
                    }
                    if (m === 'datosgob') {
                      setDatosGobPreviewData(null);
                      setDatosGobResult('');
                    }
                    if (m === 'dataset') setDatasetPreviewData(null);
                  }}
                  className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${uploadMode === m ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30' : 'text-gray-400 border-white/10 hover:text-white'}`}
                >
                  {m === 'file'
                    ? 'Archivo'
                    : m === 'text'
                      ? 'Texto'
                      : m === 'url'
                        ? 'URL'
                        : m === 'scrape'
                          ? 'Scrape archivos'
                          : m === 'dataset'
                            ? 'Datasets'
                            : m === 'tainacan'
                              ? 'Tainacan'
                              : 'datos.gob.mx'}
                </button>
              ))}
            </div>

            {uploadMode === 'dataset' ? (
              <div className="space-y-4">
                <div className="flex gap-3">
                  <input
                    type="url"
                    value={datasetUrl}
                    onChange={(e) => setDatasetUrl(e.target.value)}
                    placeholder="https://datos.gob.mx/... o https://riisp.insp.mx/nada/..."
                    className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-cyan-500/50"
                  />
                  <input
                    type="text"
                    value={uploadCategory}
                    onChange={(e) => setUploadCategory(e.target.value)}
                    placeholder="Categoría"
                    className="w-40 bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-cyan-500/50"
                  />
                  <button
                    onClick={handleDatasetPreview}
                    disabled={datasetLoading || !datasetUrl.trim()}
                    className="bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 border border-purple-500/30 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-40 flex items-center gap-2 whitespace-nowrap"
                  >
                    {datasetLoading ? (
                      <>
                        <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                        Escaneando...
                      </>
                    ) : (
                      'Buscar recursos'
                    )}
                  </button>
                </div>
                {datasetPreviewData && datasetPreviewData.resources.length > 0 && (
                  <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
                    <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/10 bg-white/5">
                      <span className="text-white text-sm font-medium">{datasetPreviewData.resources.length} recursos encontrados</span>
                      <div className="flex gap-2">
                        <button onClick={() => toggleAllDatasetResources(true)} className="text-xs text-cyan-400 hover:text-cyan-300">
                          Seleccionar todos
                        </button>
                        <span className="text-gray-600">|</span>
                        <button onClick={() => toggleAllDatasetResources(false)} className="text-xs text-gray-400 hover:text-white">
                          Deseleccionar
                        </button>
                      </div>
                    </div>
                    <div className="max-h-72 overflow-y-auto custom-scrollbar divide-y divide-white/5">
                      {datasetPreviewData.resources.map((res, idx) => (
                        <label
                          key={idx}
                          className="flex items-start gap-3 px-4 py-2.5 hover:bg-white/5 cursor-pointer transition-colors"
                        >
                          <input
                            type="checkbox"
                            checked={res.selected}
                            onChange={() =>
                              setDatasetPreviewData((prev) =>
                                prev
                                  ? { ...prev, resources: prev.resources.map((r, i) => (i === idx ? { ...r, selected: !r.selected } : r)) }
                                  : prev
                              )
                            }
                            className="mt-1 rounded border-gray-500 bg-white/10 text-cyan-500 focus:ring-cyan-500/30"
                          />
                          <div className="min-w-0 flex-1">
                            <p className="text-white text-sm truncate">{res.title}</p>
                            {res.description && <p className="text-gray-500 text-xs truncate">{res.description}</p>}
                            <p className="text-gray-600 text-xs truncate">{res.url}</p>
                          </div>
                          {res.format && (
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/10 text-gray-400 uppercase flex-shrink-0">
                              {res.format}
                            </span>
                          )}
                        </label>
                      ))}
                    </div>
                    <div className="px-4 py-3 border-t border-white/10 bg-white/5">
                      <button
                        onClick={handleDatasetIndex}
                        disabled={uploading || datasetPreviewData.resources.filter((r) => r.selected).length === 0}
                        className="w-full bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/30 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-40 flex items-center justify-center gap-2"
                      >
                        {uploading ? (
                          <>
                            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                            </svg>
                            Indexando...
                          </>
                        ) : (
                          <>Indexar {datasetPreviewData.resources.filter((r) => r.selected).length} recursos seleccionados</>
                        )}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : uploadMode === 'tainacan' ? (
              <div className="space-y-4">
                <div className="flex gap-3 items-end">
                  <div className="flex-1">
                    <p className="text-gray-400 text-sm mb-2">
                      Importar las 1,400+ fuentes curadas desde la colección Tainacan de ominis.org.
                    </p>
                  </div>
                  <input
                    type="text"
                    value={uploadCategory}
                    onChange={(e) => setUploadCategory(e.target.value)}
                    placeholder="Categoría"
                    className="w-40 bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-cyan-500/50"
                  />
                  <button
                    onClick={handleTainacanPreview}
                    disabled={tainacanLoading}
                    className="bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 border border-purple-500/30 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-40 flex items-center gap-2 whitespace-nowrap"
                  >
                    {tainacanLoading ? (
                      <>
                        <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                        Conectando...
                      </>
                    ) : (
                      'Vista previa'
                    )}
                  </button>
                </div>
                {tainacanPreviewData && (
                  <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
                    <div className="px-4 py-3 border-b border-white/10 bg-white/5">
                      <span className="text-white text-sm font-medium">{tainacanPreviewData.totalItems} fuentes encontradas</span>
                    </div>
                    <div className="px-4 py-3 border-t border-white/10 bg-white/5">
                      <button
                        onClick={handleTainacanImport}
                        disabled={tainacanImporting}
                        className="flex-1 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/30 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-40 flex items-center justify-center gap-2"
                      >
                        {tainacanImporting ? (
                          <>
                            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                            </svg>
                            Importando...
                          </>
                        ) : (
                          <>Importar {tainacanPreviewData.totalItems} fuentes de Tainacan</>
                        )}
                      </button>
                    </div>
                  </div>
                )}
                {tainacanResult && (
                  <div className="bg-cyan-500/10 border border-cyan-500/20 rounded-lg px-4 py-3 text-cyan-300 text-sm">
                    {tainacanResult}
                  </div>
                )}
              </div>
            ) : uploadMode === 'datosgob' ? (
              <div className="space-y-4">
                <div className="flex gap-3 items-end flex-wrap">
                  <div className="flex-1 min-w-[min(100%,20rem)]">
                    <p className="text-gray-400 text-sm mb-2">
                      Importar metadatos de conjuntos del grupo CKAN «Salud» en{' '}
                      <a
                        href="https://www.datos.gob.mx/dataset/?groups=salud"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-cyan-400 hover:underline"
                      >
                        datos.gob.mx
                      </a>{' '}
                      vía API oficial (sin descargar el CSV completo: se indexan descripción, institución, etiquetas y
                      enlaces de descarga).
                    </p>
                    <p className="text-gray-500 text-xs">
                      El conteo del catálogo CKAN puede diferir del número mostrado en la web; la importación usa el API{' '}
                      <code className="text-gray-400">package_search</code> con grupo <code className="text-gray-400">salud</code>.
                    </p>
                  </div>
                  <input
                    type="text"
                    value={uploadCategory}
                    onChange={(e) => setUploadCategory(e.target.value)}
                    placeholder="Categoría"
                    className="w-40 bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-cyan-500/50"
                  />
                  <button
                    onClick={() => void handleDatosGobPreview()}
                    disabled={datosGobLoading}
                    className="bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 border border-purple-500/30 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-40 flex items-center gap-2 whitespace-nowrap"
                  >
                    {datosGobLoading ? (
                      <>
                        <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                        Consultando CKAN…
                      </>
                    ) : (
                      'Vista previa'
                    )}
                  </button>
                </div>
                {datosGobPreviewData && (
                  <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden space-y-3">
                    <div className="px-4 py-3 border-b border-white/10 bg-white/5">
                      <p className="text-white text-sm font-medium">
                        {datosGobPreviewData.totalPackages} conjuntos en grupo «{datosGobPreviewData.groupTitle || datosGobPreviewData.groupName}»
                      </p>
                      <p className="text-gray-500 text-xs mt-1">
                        Muestra recursos en la primera página: {datosGobPreviewData.totalResourcesSample} recursos; formatos:{' '}
                        {Object.entries(datosGobPreviewData.resourceFormatsSample || {})
                          .map(([k, v]) => `${k}: ${v}`)
                          .join(' · ') || '—'}
                      </p>
                    </div>
                    {datosGobPreviewData.sampleTitles.length > 0 && (
                      <ul className="px-4 text-xs text-gray-400 list-disc list-inside space-y-0.5 pb-2">
                        {datosGobPreviewData.sampleTitles.slice(0, 6).map((t) => (
                          <li key={t}>{t}</li>
                        ))}
                      </ul>
                    )}
                    <div className="px-4 py-3 border-t border-white/10 bg-white/5">
                      <button
                        onClick={() => void handleDatosGobImport()}
                        disabled={datosGobImporting}
                        className="w-full bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/30 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-40 flex items-center justify-center gap-2"
                      >
                        {datosGobImporting ? (
                          <>
                            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                            </svg>
                            Importando metadatos…
                          </>
                        ) : (
                          <>Importar {datosGobPreviewData.totalPackages} conjuntos (metadatos)</>
                        )}
                      </button>
                    </div>
                  </div>
                )}
                {datosGobResult && (
                  <div className="bg-cyan-500/10 border border-cyan-500/20 rounded-lg px-4 py-3 text-cyan-300 text-sm">
                    {datosGobResult}
                  </div>
                )}
              </div>
            ) : uploadMode === 'scrape' ? (
              <div className="space-y-4">
                <div className="flex gap-3">
                  <input
                    type="url"
                    value={scrapeUrl}
                    onChange={(e) => setScrapeUrl(e.target.value)}
                    placeholder="https://riisp.insp.mx/nada/... o https://www.gob.mx/.../documentos"
                    className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-cyan-500/50"
                  />
                  <input
                    type="text"
                    value={uploadCategory}
                    onChange={(e) => setUploadCategory(e.target.value)}
                    placeholder="Categoría"
                    className="w-40 bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-cyan-500/50"
                  />
                  <button
                    onClick={handleScrapePreview}
                    disabled={scrapeLoading || !scrapeUrl.trim()}
                    className="bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 border border-purple-500/30 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-40 flex items-center gap-2 whitespace-nowrap"
                  >
                    {scrapeLoading ? (
                      <>
                        <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                        Escaneando...
                      </>
                    ) : (
                      'Buscar archivos'
                    )}
                  </button>
                </div>
                {scrapePreviewDone && scrapedFiles.length > 0 && (
                  <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
                    <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/10 bg-white/5">
                      <span className="text-white text-sm font-medium">{scrapedFiles.length} archivos encontrados (PDF, CSV, XLS)</span>
                      <div className="flex gap-2">
                        <button onClick={() => toggleAllScrapedFiles(true)} className="text-xs text-cyan-400 hover:text-cyan-300">
                          Seleccionar todos
                        </button>
                        <span className="text-gray-600">|</span>
                        <button onClick={() => toggleAllScrapedFiles(false)} className="text-xs text-gray-400 hover:text-white">
                          Deseleccionar
                        </button>
                      </div>
                    </div>
                    <div className="max-h-72 overflow-y-auto custom-scrollbar divide-y divide-white/5">
                      {scrapedFiles.map((file, idx) => (
                        <label
                          key={idx}
                          className="flex items-start gap-3 px-4 py-2.5 hover:bg-white/5 cursor-pointer transition-colors"
                        >
                          <input
                            type="checkbox"
                            checked={file.selected}
                            onChange={() =>
                              setScrapedFiles((prev) => prev.map((p, i) => (i === idx ? { ...p, selected: !p.selected } : p)))
                            }
                            className="mt-1 rounded border-gray-500 bg-white/10 text-cyan-500 focus:ring-cyan-500/30"
                          />
                          <div className="min-w-0 flex-1">
                            <p className="text-white text-sm truncate">{file.title}</p>
                            <p className="text-gray-500 text-xs truncate">{file.fileUrl}</p>
                          </div>
                          {file.format && (
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/10 text-gray-400 uppercase flex-shrink-0">
                              {file.format}
                            </span>
                          )}
                        </label>
                      ))}
                    </div>
                    <div className="px-4 py-3 border-t border-white/10 bg-white/5">
                      <button
                        onClick={handleScrapeIndex}
                        disabled={uploading || scrapedFiles.filter((p) => p.selected).length === 0}
                        className="w-full bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/30 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-40 flex items-center justify-center gap-2"
                      >
                        {uploading ? (
                          <>
                            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                            </svg>
                            Indexando...
                          </>
                        ) : (
                          <>Indexar {scrapedFiles.filter((p) => p.selected).length} archivos seleccionados</>
                        )}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <div className="lg:col-span-2 space-y-3">
                  {uploadMode === 'file' && (
                    <div
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={handleFileDrop}
                      className="border-2 border-dashed border-white/20 rounded-xl p-6 text-center hover:border-cyan-500/40 transition-colors cursor-pointer"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".pdf,.docx,.txt,.html,.htm,.csv,.xlsx,.xls,.sav,.zip"
                        className="hidden"
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          if (f) setUploadFile(f);
                        }}
                      />
                      {uploadFile ? (
                        <div>
                          <p className="text-cyan-300 font-medium">{uploadFile.name}</p>
                          <p className="text-gray-500 text-xs mt-1">{(uploadFile.size / 1024).toFixed(1)} KB</p>
                        </div>
                      ) : (
                        <div>
                          <p className="text-gray-400">Arrastra un archivo o haz clic</p>
                          <p className="text-gray-500 text-xs mt-1">PDF, DOCX, TXT, HTML, CSV, XLS, XLSX, SAV, ZIP</p>
                        </div>
                      )}
                    </div>
                  )}
                  {uploadMode === 'text' && (
                    <textarea
                      value={uploadText}
                      onChange={(e) => setUploadText(e.target.value)}
                      placeholder="Pega texto para indexar..."
                      rows={6}
                      className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-cyan-500/50 resize-none"
                    />
                  )}
                  {uploadMode === 'url' && (
                    <div className="space-y-2">
                      <textarea
                        value={uploadUrl}
                        onChange={(e) => setUploadUrl(e.target.value)}
                        placeholder="Una o más URLs (una por línea)&#10;https://www.gob.mx/salud&#10;https://www.imss.gob.mx"
                        rows={4}
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-cyan-500/50 resize-y"
                      />
                      <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={uploadFollowLinks}
                          onChange={(e) => setUploadFollowLinks(e.target.checked)}
                          className="rounded border-gray-500 bg-white/10 text-cyan-500 focus:ring-cyan-500/30"
                        />
                        Seguir enlaces encontrados en estas URLs (crawl mismo dominio)
                      </label>
                    </div>
                  )}
                </div>
                <div className="space-y-3">
                  <input
                    type="text"
                    value={uploadTitle}
                    onChange={(e) => setUploadTitle(e.target.value)}
                    placeholder="Título (opcional)"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-cyan-500/50"
                  />
                  <input
                    type="text"
                    value={uploadCategory}
                    onChange={(e) => setUploadCategory(e.target.value)}
                    placeholder="Categoría"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-cyan-500/50"
                  />
                  <button
                    onClick={handleUpload}
                    disabled={
                      uploading ||
                      (uploadMode === 'file' && !uploadFile) ||
                      (uploadMode === 'text' && !uploadText.trim()) ||
                      (uploadMode === 'url' && !uploadUrl.trim())
                    }
                    className="w-full bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/30 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-40 flex items-center justify-center gap-2"
                  >
                    {uploading ? (
                      <>
                        <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                        Indexando...
                      </>
                    ) : (
                      'Indexar Fuente'
                    )}
                  </button>
                </div>
              </div>
            )}
          </Section>
        </div>

        {/* Search & Filter */}
        <Section
          title="Buscar y filtrar"
          action={
            <button
              onClick={handleBatchReindex}
              className="text-xs px-2 py-1 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 hover:bg-amber-500/30"
            >
              Re-indexar con taxonomía
            </button>
          }
        >
          <div className="space-y-4">
            <div className="flex flex-wrap gap-3">
              <input
                type="text"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setSourcesPage(1);
                }}
                onKeyDown={(e) => e.key === 'Enter' && loadSources()}
                placeholder="Buscar por título, descripción, editor..."
                className="flex-1 min-w-[200px] bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-cyan-500/50"
              />
              <button
                onClick={loadSources}
                disabled={sourcesLoading}
                className="bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/30 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors disabled:opacity-40 flex items-center gap-2"
              >
                {sourcesLoading ? (
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  'Buscar'
                )}
              </button>
            </div>

            {taxonomySchema && Object.keys(taxonomySchema).length > 0 && (
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-2">
                {Object.entries(taxonomySchema).map(([dim, values]) => {
                  const selected = taxonomyFilters[dim] || [];
                  const selectedPreview = selected.slice(0, 2).join(', ');
                  const hasMoreSelected = selected.length > 2;
                  return (
                    <details
                      key={dim}
                      className="group bg-white/5 border border-white/10 rounded-lg"
                    >
                      <summary className="list-none cursor-pointer px-3 py-2 flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-gray-300 text-[11px] font-medium truncate">{DIM_LABELS[dim] || dim}</p>
                          <p className="text-gray-500 text-[10px] truncate">
                            {selected.length > 0
                              ? `${selectedPreview}${hasMoreSelected ? ', ...' : ''}`
                              : 'Sin selección'}
                          </p>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          {selected.length > 0 && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                              {selected.length}
                            </span>
                          )}
                          <svg
                            className="w-3.5 h-3.5 text-gray-400 transition-transform group-open:rotate-180"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                          </svg>
                        </div>
                      </summary>

                      <div className="px-3 pb-2 border-t border-white/10">
                        <div className="pt-2 max-h-36 overflow-y-auto custom-scrollbar space-y-1">
                          {values.map((v) => (
                            <label key={v} className="flex items-center gap-2 cursor-pointer hover:bg-white/5 rounded px-1 -mx-1">
                              <input
                                type="checkbox"
                                checked={selected.includes(v)}
                                onChange={(e) => {
                                  const next = e.target.checked
                                    ? [...selected, v]
                                    : selected.filter((x) => x !== v);
                                  setTaxonomyFilter(dim, next);
                                }}
                                className="rounded border-gray-500 bg-white/10 text-cyan-500 focus:ring-cyan-500/30"
                              />
                              <span className="text-white text-xs truncate">{v}</span>
                            </label>
                          ))}
                        </div>
                        {selected.length > 0 && (
                          <button
                            onClick={() => setTaxonomyFilter(dim, [])}
                            className="text-[10px] text-gray-500 hover:text-white mt-1"
                          >
                            Limpiar
                          </button>
                        )}
                      </div>
                    </details>
                  );
                })}
              </div>
            )}
          </div>
        </Section>

        {/* Sources table */}
        <Section
          title={`Fuentes DataStore (${totalSources})`}
          action={
            <div className="flex flex-wrap gap-1 justify-end">
              <button
                type="button"
                onClick={handleReconcileStatus}
                disabled={reconciling}
                className="text-xs px-2 py-1 rounded bg-emerald-500/15 text-emerald-200 border border-emerald-500/30 hover:bg-emerald-500/25 disabled:opacity-50"
                title="Para fuentes en error: si ya hay vectores en el almacén, pasa el estado a activo y sincroniza el conteo"
              >
                {reconciling ? '…' : 'Corregir errores con vectores'}
              </button>
              <button
                type="button"
                onClick={handleMarkStuckAsFailed}
                disabled={markingStuck}
                className="text-xs px-2 py-1 rounded bg-red-500/20 text-red-300 border border-red-500/30 hover:bg-red-500/30 disabled:opacity-50"
                title="Fuentes en 'indexando' sin actualizar &gt;30 min: si hay vectores → activas; si no → error (reindex)"
              >
                {markingStuck ? '…' : 'Marcar atascadas como fallidas'}
              </button>
            </div>
          }
        >
          {sourcesLoading ? (
            <p className="text-gray-500 text-sm">Cargando...</p>
          ) : sources.length > 0 ? (
            <div className="space-y-2">
              <div className="max-h-[500px] overflow-y-auto custom-scrollbar space-y-2 pr-1">
                {sources.map((s) => (
                  <div key={s.id} className="bg-white/5 rounded-lg px-3 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-white text-sm truncate">{s.title}</p>
                        <p className="text-gray-500 text-xs">
                          {s.sourceType} · {s.chunksCount} chunks
                          {s.publisher && <> · {s.publisher}</>}
                          {s.documentDate && <> · Publicación: {s.documentDate}</>}
                          {s.lastIndexedAt && (
                            <>
                              {' '}
                              · Ingesta:{' '}
                              {new Date(s.lastIndexedAt).toLocaleString('es-MX', {
                                dateStyle: 'short',
                                timeStyle: 'short',
                              })}
                            </>
                          )}
                        </p>
                        {s.description && <p className="text-gray-500 text-[10px] truncate mt-0.5">{s.description}</p>}
                        {s.taxonomy && Object.keys(s.taxonomy).length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1">
                            {Object.entries(s.taxonomy).map(([dim, vals]) =>
                              (vals || []).map((v) => (
                                <span
                                  key={`${dim}-${v}`}
                                  className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                                >
                                  {v}
                                </span>
                              ))
                            )}
                          </div>
                        )}
                        {s.indexingError && (
                          <p className="text-red-300/90 text-[10px] mt-1 break-words leading-snug">
                            {s.indexingError}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <StatusBadge status={s.status} />
                        <button
                          onClick={() => handleViewChunks(s.id)}
                          title="Ver chunks"
                          className="p-1 text-gray-400 hover:text-cyan-300 transition-colors"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                          </svg>
                        </button>
                        <button
                          onClick={() => handleClassify(s.id)}
                          title="Clasificar taxonomía"
                          className="p-1 text-gray-400 hover:text-purple-300 transition-colors"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                          </svg>
                        </button>
                        <button
                          onClick={() => handleReindex(s.id)}
                          title="Re-indexar"
                          className="p-1 text-gray-400 hover:text-amber-300 transition-colors"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                          </svg>
                        </button>
                        <button
                          onClick={() => handleDeleteSource(s.id, s.title)}
                          title="Eliminar"
                          className="p-1 text-gray-400 hover:text-red-300 transition-colors"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    </div>
                    {viewingChunks === s.id && (
                      <div className="mt-2 pt-2 border-t border-white/10">
                        {chunksLoading ? (
                          <p className="text-gray-500 text-xs">Cargando chunks...</p>
                        ) : chunks.length > 0 ? (
                          <div className="space-y-1.5 max-h-40 overflow-y-auto custom-scrollbar">
                            {chunks.map((c, i) => (
                              <div key={c.id || i} className="bg-white/5 rounded px-2 py-1.5">
                                <p className="text-gray-300 text-xs leading-relaxed">{c.contentPreview}</p>
                                {c.url && <p className="text-cyan-500/60 text-[10px] mt-0.5 truncate">{c.url}</p>}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-gray-500 text-xs">
                            {s.indexingError
                              ? s.indexingError
                              : s.chunksCount > 0
                                ? 'No se encontraron vectores en el almacén para esta fuente (p. ej. metadatos desincronizados). Prueba re-indexar o informa al equipo.'
                                : 'No hay chunks para esta fuente.'}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <div className="flex items-center justify-between pt-3 border-t border-white/10">
                <span className="text-gray-500 text-xs">
                  Página {sourcesPage} de {Math.ceil(totalSources / pageSize) || 1} · {totalSources} total
                </span>
                <div className="flex gap-1">
                  <button
                    onClick={() => setSourcesPage((p) => Math.max(1, p - 1))}
                    disabled={sourcesPage <= 1}
                    className="px-2 py-1 text-xs rounded bg-white/5 text-gray-400 hover:text-white disabled:opacity-40"
                  >
                    Anterior
                  </button>
                  <button
                    onClick={() => setSourcesPage((p) => p + 1)}
                    disabled={sourcesPage * pageSize >= totalSources}
                    className="px-2 py-1 text-xs rounded bg-white/5 text-gray-400 hover:text-white disabled:opacity-40"
                  >
                    Siguiente
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <p className="text-gray-500 text-sm">No hay fuentes. Usa el formulario de arriba para agregar una.</p>
          )}
        </Section>
      </main>
    </div>
  );
}
