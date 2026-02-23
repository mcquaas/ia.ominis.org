'use client';

import { useState, useEffect, useCallback } from 'react';
import Header from '@/components/Header';
import { useAuth } from '@/hooks/useAuth';
import { listCubes, getCubeMetadata, queryCube, getProxyStatus } from '@/services/sinba';
import type { CubeMetadata, CubeQueryResult } from '@/services/sinba';

/* ────────── Tiny UI components ────────── */

function Badge({ children, color = 'cyan' }: { children: React.ReactNode; color?: string }) {
  const map: Record<string, string> = {
    cyan: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
    green: 'bg-green-500/20 text-green-300 border-green-500/30',
    amber: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
    purple: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
    blue: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-xs rounded-full border ${map[color] || map.cyan}`}>
      {children}
    </span>
  );
}

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

/* ────────── Category colors ────────── */
function categoryColor(cat: string): string {
  const c = cat.toLowerCase();
  if (c.includes('defuncion') || c.includes('mortal') || c.includes('fetal')) return 'amber';
  if (c.includes('egreso') || c.includes('saeh') || c.includes('prod') || c.includes('lesion') || c.includes('urgencia')) return 'cyan';
  if (c.includes('nacimiento') || c.includes('sinac')) return 'green';
  if (c.includes('servicio') || c.includes('sis')) return 'purple';
  if (c.includes('recurso') || c.includes('cuenta') || c.includes('conapo')) return 'blue';
  return 'cyan';
}

/* ────────── Main page ────────── */
export default function SinbaPage() {
  const { loading: authLoading, isAdmin } = useAuth();
  // Cube list state
  const [cubePages, setCubePages] = useState<{ filename: string; label: string; category: string }[]>([]);
  const [loadingCubes, setLoadingCubes] = useState(true);
  const [searchFilter, setSearchFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');

  // Selected cube state
  const [selectedCubeId, setSelectedCubeId] = useState('');
  const [cubeMetadata, setCubeMetadata] = useState<CubeMetadata | null>(null);
  const [loadingMeta, setLoadingMeta] = useState(false);

  // Query state
  const [question, setQuestion] = useState('');
  const [mdxMode, setMdxMode] = useState(false);
  const [mdxQuery, setMdxQuery] = useState('');
  const [queryResult, setQueryResult] = useState<CubeQueryResult | null>(null);
  const [querying, setQuerying] = useState(false);
  const [error, setError] = useState('');

  // Proxy status (XMLA proxy must be running to query cubes)
  const [proxyHealthy, setProxyHealthy] = useState<boolean | null>(null);
  const [proxyError, setProxyError] = useState<string>('');

  // Load cube list and proxy status on mount
  useEffect(() => {
    listCubes()
      .then(data => setCubePages(data.cubes || []))
      .catch(err => setError(err.message))
      .finally(() => setLoadingCubes(false));

    getProxyStatus()
      .then(s => {
        setProxyHealthy(s.healthy);
        setProxyError(s.error || '');
      })
      .catch(() => {
        setProxyHealthy(false);
        setProxyError('No se pudo verificar el estado del proxy');
      });
  }, []);

  // Load cube metadata when selected
  const selectCube = useCallback(async (cubeId: string) => {
    setSelectedCubeId(cubeId);
    setCubeMetadata(null);
    setQueryResult(null);
    setError('');
    setLoadingMeta(true);

    try {
      const meta = await getCubeMetadata(cubeId);
      setCubeMetadata(meta);
    } catch (err: any) {
      setError(err.message || 'Failed to load cube metadata');
    } finally {
      setLoadingMeta(false);
    }
  }, []);

  // Execute query
  const handleQuery = useCallback(async () => {
    if (!selectedCubeId) return;
    if (!mdxMode && !question.trim()) return;
    if (mdxMode && !mdxQuery.trim()) return;

    setQuerying(true);
    setError('');
    setQueryResult(null);

    try {
      const result = await queryCube({
        question: mdxMode ? '' : question,
        cube_id: selectedCubeId,
        mdx_query: mdxMode ? mdxQuery : '',
        max_rows: 500,
      });
      setQueryResult(result);
      if (!result.success && result.error) {
        setError(result.error);
      }
    } catch (err: any) {
      setError(err.message || 'Query failed');
    } finally {
      setQuerying(false);
    }
  }, [selectedCubeId, question, mdxMode, mdxQuery]);

  // Export results to CSV
  const exportCSV = useCallback(() => {
    if (!queryResult?.rows?.length) return;
    const cols = queryResult.columns;
    const lines = [cols.join(',')];
    for (const row of queryResult.rows) {
      lines.push(cols.map(c => {
        const v = String(row[c] ?? '');
        return v.includes(',') || v.includes('"') ? `"${v.replace(/"/g, '""')}"` : v;
      }).join(','));
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `sinba_${selectedCubeId}_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [queryResult, selectedCubeId]);

  // Filter cubes
  const categories = Array.from(new Set(cubePages.map(c => c.category).filter(Boolean)));
  const filteredCubes = cubePages.filter(c => {
    const matchesSearch = !searchFilter || c.label.toLowerCase().includes(searchFilter.toLowerCase()) || c.filename.toLowerCase().includes(searchFilter.toLowerCase());
    const matchesCat = !categoryFilter || c.category === categoryFilter;
    return matchesSearch && matchesCat;
  });

  if (!authLoading && !isAdmin) {
    return (
      <div className="min-h-screen bg-[#0a1628] text-gray-100">
        <Header />
        <main className="pt-20 pb-10 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto text-center py-16">
          <p className="text-gray-400">Necesitas permisos de administrador para acceder a Cubos SINBA.</p>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a1628] text-gray-100">
      <Header />

      <main className="pt-20 pb-10 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
        {/* Proxy status banner */}
        {proxyHealthy === false && (
          <div className="mb-6 p-4 bg-amber-500/10 border border-amber-500/30 rounded-xl flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-amber-300 font-medium">Consulta de datos no disponible</p>
              <p className="text-amber-200/80 text-sm mt-1">
                {proxyError || 'El proxy XMLA no está disponible.'} Las consultas requieren el proxy .NET en ejecución. Puedes explorar metadatos o ver la fuente en SINBA.
              </p>
            </div>
            <button
              onClick={() =>
                getProxyStatus()
                  .then(s => {
                    setProxyHealthy(s.healthy);
                    setProxyError(s.error || '');
                  })
                  .catch(() => setProxyHealthy(false))
              }
              className="text-xs px-3 py-1.5 rounded border border-amber-500/50 text-amber-300 hover:bg-amber-500/20 transition-colors"
            >
              Reintentar
            </button>
          </div>
        )}

        {/* Page Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white flex items-center gap-3">
            <svg className="w-8 h-8 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
            </svg>
            Cubos SINBA
          </h1>
          <p className="text-gray-400 mt-2 max-w-3xl">
            Consulta los cubos OLAP del Sistema Nacional de Informaci&oacute;n B&aacute;sica en Salud (SINBA) de la Secretar&iacute;a de Salud de M&eacute;xico.
            Datos de egresos hospitalarios, mortalidad, nacimientos, servicios de salud y m&aacute;s.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* ── Left panel: Cube browser ── */}
          <div className="lg:col-span-1 space-y-4">
            <Section title={`Cubos disponibles (${filteredCubes.length})`}>
              {/* Search */}
              <input
                type="text"
                placeholder="Buscar cubo..."
                value={searchFilter}
                onChange={e => setSearchFilter(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500/50 mb-3"
              />

              {/* Category filter */}
              <div className="flex flex-wrap gap-1 mb-3">
                <button
                  onClick={() => setCategoryFilter('')}
                  className={`text-xs px-2 py-1 rounded-full border transition-colors ${!categoryFilter ? 'bg-cyan-500/20 border-cyan-500/50 text-cyan-300' : 'border-white/10 text-gray-400 hover:border-white/20'}`}
                >
                  Todos
                </button>
                {categories.slice(0, 8).map(cat => (
                  <button
                    key={cat}
                    onClick={() => setCategoryFilter(categoryFilter === cat ? '' : cat)}
                    className={`text-xs px-2 py-1 rounded-full border transition-colors truncate max-w-[150px] ${categoryFilter === cat ? 'bg-cyan-500/20 border-cyan-500/50 text-cyan-300' : 'border-white/10 text-gray-400 hover:border-white/20'}`}
                    title={cat}
                  >
                    {cat.length > 20 ? cat.slice(0, 20) + '...' : cat}
                  </button>
                ))}
              </div>

              {/* Cube list */}
              <div className="max-h-[60vh] overflow-y-auto space-y-1 pr-1 scrollbar-thin">
                {loadingCubes ? (
                  <div className="text-center py-8 text-gray-500">
                    <div className="animate-spin w-6 h-6 border-2 border-cyan-500/30 border-t-cyan-400 rounded-full mx-auto mb-2" />
                    Cargando cubos...
                  </div>
                ) : filteredCubes.length === 0 ? (
                  <p className="text-gray-500 text-sm py-4 text-center">No se encontraron cubos</p>
                ) : (
                  filteredCubes.map(cube => {
                    const cubeId = cube.filename.replace('.html', '');
                    const isSelected = cubeId === selectedCubeId;
                    return (
                      <button
                        key={cube.filename}
                        onClick={() => selectCube(cubeId)}
                        className={`w-full text-left px-3 py-2 rounded-lg transition-colors text-sm ${isSelected ? 'bg-cyan-500/20 border border-cyan-500/30 text-white' : 'hover:bg-white/5 text-gray-300 border border-transparent'}`}
                      >
                        <div className="font-medium truncate">{cube.label}</div>
                        <div className="text-xs text-gray-500 truncate mt-0.5">{cube.filename}</div>
                      </button>
                    );
                  })
                )}
              </div>
            </Section>
          </div>

          {/* ── Right panel: Metadata + Query ── */}
          <div className="lg:col-span-2 space-y-4">
            {/* Cube metadata */}
            {loadingMeta && (
              <Section title="Cargando metadatos...">
                <div className="flex items-center gap-3 text-gray-400">
                  <div className="animate-spin w-5 h-5 border-2 border-cyan-500/30 border-t-cyan-400 rounded-full" />
                  Analizando cubo OLAP...
                </div>
              </Section>
            )}

            {cubeMetadata && (
              <Section title={cubeMetadata.name || cubeMetadata.cube_id}>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-4">
                  <div>
                    <p className="text-xs text-gray-500 uppercase">Cat&aacute;logo</p>
                    <p className="text-sm text-white font-medium">{cubeMetadata.connection.catalog || '—'}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500 uppercase">Servidor</p>
                    <p className="text-sm text-white font-medium truncate">{cubeMetadata.connection.server || '—'}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500 uppercase">A&ntilde;o</p>
                    <p className="text-sm text-white font-medium">{cubeMetadata.year || '—'}</p>
                  </div>
                  {cubeMetadata.publication_date && (
                    <div>
                      <p className="text-xs text-gray-500 uppercase">Publicaci&oacute;n</p>
                      <p className="text-sm text-gray-300">{cubeMetadata.publication_date}</p>
                    </div>
                  )}
                  {cubeMetadata.is_preliminary && (
                    <div className="col-span-2">
                      <Badge color="amber">Datos preliminares</Badge>
                    </div>
                  )}
                </div>

                {/* Dimensions */}
                {cubeMetadata.dimensions.length > 0 && (
                  <div className="mb-3">
                    <p className="text-xs text-gray-500 uppercase mb-1">Dimensiones</p>
                    <div className="flex flex-wrap gap-1">
                      {cubeMetadata.dimensions.map((d, i) => (
                        <Badge key={i} color="blue">{d.name || d.source_name}</Badge>
                      ))}
                    </div>
                  </div>
                )}

                {/* Measures */}
                {cubeMetadata.measures.length > 0 && (
                  <div>
                    <p className="text-xs text-gray-500 uppercase mb-1">Medidas</p>
                    <div className="flex flex-wrap gap-1">
                      {cubeMetadata.measures.map((m, i) => (
                        <Badge key={i} color="green">{m.name || m.source_name}</Badge>
                      ))}
                    </div>
                  </div>
                )}

                {cubeMetadata.url && (
                  <div className="mt-3 pt-3 border-t border-white/5">
                    <a
                      href={cubeMetadata.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
                    >
                      Ver fuente original en SINBA &rarr;
                    </a>
                  </div>
                )}
              </Section>
            )}

            {/* Query interface */}
            {selectedCubeId && cubeMetadata && (
              <Section
                title="Consultar datos"
                action={
                  <button
                    onClick={() => setMdxMode(!mdxMode)}
                    className={`text-xs px-2 py-1 rounded border transition-colors ${mdxMode ? 'bg-purple-500/20 border-purple-500/50 text-purple-300' : 'border-white/10 text-gray-400 hover:border-white/20'}`}
                  >
                    {mdxMode ? 'Modo MDX' : 'Lenguaje natural'}
                  </button>
                }
              >
                {!mdxMode ? (
                  /* Natural language mode */
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">
                      Pregunta en lenguaje natural
                    </label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={question}
                        onChange={e => setQuestion(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && handleQuery()}
                        placeholder={`Ej: &iquest;Cu&aacute;ntos productos hay por entidad?`}
                        className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500/50"
                        disabled={querying}
                      />
                      <button
                        onClick={handleQuery}
                        disabled={querying || !question.trim() || proxyHealthy === false}
                        className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
                      >
                        {querying ? (
                          <div className="animate-spin w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />
                        ) : (
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                          </svg>
                        )}
                        Consultar
                      </button>
                    </div>
                    <p className="text-xs text-gray-600 mt-1">
                      Ominis traducir&aacute; tu pregunta a MDX y consultar&aacute; el cubo OLAP
                    </p>
                  </div>
                ) : (
                  /* MDX mode */
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">
                      Consulta MDX
                    </label>
                    <textarea
                      value={mdxQuery}
                      onChange={e => setMdxQuery(e.target.value)}
                      placeholder={`SELECT NON EMPTY {[Measures].[Productos]} ON COLUMNS,\n  NON EMPTY {[DClues2025].[Unidad M\u00e9dica].[Entidad].Members} ON ROWS\nFROM [${cubeMetadata.name}]`}
                      rows={5}
                      className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white font-mono placeholder-gray-600 focus:outline-none focus:border-purple-500/50 resize-y"
                      disabled={querying}
                    />
                    <div className="flex justify-between items-center mt-2">
                      <p className="text-xs text-gray-600">
                        Cube: [{cubeMetadata.name}] &bull; Catalog: {cubeMetadata.connection.catalog}
                      </p>
                      <button
                        onClick={handleQuery}
                        disabled={querying || !mdxQuery.trim() || proxyHealthy === false}
                        className="px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
                      >
                        {querying && <div className="animate-spin w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />}
                        Ejecutar MDX
                      </button>
                    </div>
                  </div>
                )}
              </Section>
            )}

            {/* Error (from query or other) */}
            {(error || (queryResult && !queryResult.success && queryResult.error)) && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-300 text-sm">
                <p className="font-medium">Error</p>
                <p className="mt-1 text-red-400">
                  {error || (queryResult?.error ?? '')}
                </p>
              </div>
            )}

            {/* Query results */}
            {queryResult && queryResult.success && (
              <>
                {/* Summary */}
                {queryResult.natural_language_summary && (
                  <Section title="Resumen">
                    <p className="text-gray-300 text-sm whitespace-pre-wrap">
                      {queryResult.natural_language_summary}
                    </p>
                  </Section>
                )}

                {/* Generated MDX */}
                {queryResult.mdx_query && !mdxMode && (
                  <Section title="Consulta MDX generada">
                    <pre className="text-xs text-purple-300 bg-black/30 rounded-lg p-3 overflow-x-auto font-mono">
                      {queryResult.mdx_query}
                    </pre>
                  </Section>
                )}

                {/* Data table */}
                <Section
                  title={`Resultados (${queryResult.row_count} filas)`}
                  action={
                    <button
                      onClick={exportCSV}
                      className="text-xs px-2 py-1 rounded border border-white/10 text-gray-400 hover:border-green-500/50 hover:text-green-300 transition-colors flex items-center gap-1"
                    >
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3M3 17V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
                      </svg>
                      Exportar CSV
                    </button>
                  }
                >
                  <div className="overflow-x-auto max-h-[50vh] overflow-y-auto">
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 bg-[#0a1628]">
                        <tr>
                          {queryResult.columns.map(col => (
                            <th key={col} className="text-left px-3 py-2 text-xs text-gray-400 uppercase tracking-wide border-b border-white/10 whitespace-nowrap">
                              {col}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {queryResult.rows.map((row, i) => (
                          <tr key={i} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                            {queryResult.columns.map(col => (
                              <td key={col} className="px-3 py-1.5 text-gray-300 whitespace-nowrap">
                                {row[col] != null ? String(row[col]) : '—'}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {queryResult.row_count > queryResult.rows.length && (
                    <p className="text-xs text-gray-500 mt-2 text-center">
                      Mostrando {queryResult.rows.length} de {queryResult.row_count} filas
                    </p>
                  )}
                </Section>
              </>
            )}

            {/* Empty state */}
            {!selectedCubeId && !loadingCubes && (
              <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl p-12 text-center">
                <svg className="w-16 h-16 text-gray-600 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                </svg>
                <h3 className="text-lg font-medium text-gray-300 mb-2">
                  Selecciona un cubo OLAP
                </h3>
                <p className="text-gray-500 text-sm max-w-md mx-auto">
                  Elige un cubo del panel izquierdo para ver sus dimensiones, medidas y poder consultar los datos de salud de M&eacute;xico.
                </p>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
