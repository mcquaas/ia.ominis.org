/**
 * SINBA Cubes Service — API client for querying Mexico's health OLAP cubes.
 */

import { getToken } from './auth';

const API_BASE = '/api/sinba';

interface CubePage {
  filename: string;
  label: string;
  category: string;
}

interface CubeDimension {
  name: string;
  source_name: string;
  orientation: string;
}

interface CubeMeasure {
  name: string;
  source_name: string;
  number_format: string;
}

export interface CubeMetadata {
  cube_id: string;
  name: string;
  title: string;
  category: string;
  year: string;
  url: string;
  is_preliminary: boolean;
  publication_date: string;
  info_cutoff_date: string;
  connection: {
    server: string;
    catalog: string;
  };
  dimensions: CubeDimension[];
  measures: CubeMeasure[];
}

export interface CubeQueryResult {
  success: boolean;
  cube_id: string;
  cube_name: string;
  mdx_query: string;
  columns: string[];
  rows: Record<string, string | number | null>[];
  row_count: number;
  error: string;
  natural_language_summary: string;
}

async function sinbaFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: { ...headers, ...(options.headers as Record<string, string> || {}) },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      error.error || error.detail || error.message || `HTTP ${response.status}`
    );
  }

  return response.json();
}

/**
 * Check if the XMLA proxy is reachable.
 */
export async function getProxyStatus(): Promise<{
  healthy: boolean;
  error?: string;
  hint?: string;
  proxy_url?: string;
}> {
  const res = await fetch(`${API_BASE}/proxy-status`);
  const data = await res.json().catch(() => ({}));
  return {
    healthy: data.healthy === true,
    error: data.error,
    hint: data.hint,
    proxy_url: data.proxy_url,
  };
}

/**
 * List all available SINBA cube pages.
 */
export async function listCubes(): Promise<{ cubes: CubePage[]; total: number }> {
  return sinbaFetch('/cubes');
}

/**
 * Get full metadata for a specific cube.
 */
export async function getCubeMetadata(cubeId: string): Promise<CubeMetadata> {
  return sinbaFetch(`/cubes/${encodeURIComponent(cubeId)}`);
}

/**
 * Query a cube with natural language or MDX.
 */
export async function queryCube(params: {
  question: string;
  cube_id: string;
  mdx_query?: string;
  max_rows?: number;
}): Promise<CubeQueryResult> {
  return sinbaFetch('/query', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

/**
 * Test connection to a cube's SSAS server.
 */
export async function testConnection(cubeId: string): Promise<{
  connected: boolean;
  server: string;
  catalog: string;
  cube_name: string;
  error: string;
}> {
  return sinbaFetch('/test-connection', {
    method: 'POST',
    body: JSON.stringify({ cube_id: cubeId }),
  });
}

/**
 * Scan the full SINBA catalog (slow, discovers all cubes).
 */
export async function fullCatalog(maxCubes = 0): Promise<{
  total: number;
  cubes: CubeMetadata[];
}> {
  const params = maxCubes > 0 ? `?max_cubes=${maxCubes}` : '';
  return sinbaFetch(`/catalog${params}`);
}
