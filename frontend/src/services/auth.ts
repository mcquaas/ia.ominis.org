/**
 * Authentication Service for Ominis Health
 * Handles user authentication, API key management, and admin functions
 */

import type {
  User,
  HealthSnapshot,
  AuthResponse,
  LoginCredentials,
  RegisterData,
  ApiKey,
  ApiKeyRecentRequest,
  CreateApiKeyData,
  CreateApiKeyResponse,
  RagSource,
  SystemStats,
  QuerySeries,
  QueryStats,
  UserUsage,
  TaxonomyDict,
  DashboardOverview,
} from '@/types/auth';

// Configuration - Haystack backend API URL
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_PREFIX = '/v1';

// Token storage key
const TOKEN_KEY = 'ominis_auth_token';
const USER_KEY = 'ominis_user';

/**
 * Get stored authentication token
 */
export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * Get stored user info
 */
export function getUser(): User | null {
  if (typeof window === 'undefined') return null;
  const userJson = localStorage.getItem(USER_KEY);
  if (!userJson) return null;
  try {
    return JSON.parse(userJson);
  } catch {
    return null;
  }
}

/**
 * Store authentication data (exported for OAuth callback)
 */
export function storeAuth(jwt: string, user: User): void {
  localStorage.setItem(TOKEN_KEY, jwt);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

/**
 * Clear authentication data
 */
export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

/**
 * Check if user is authenticated
 */
export function isAuthenticated(): boolean {
  return !!getToken();
}

/**
 * Check if user has a specific role
 */
export function hasRole(role: 'researcher' | 'developer' | 'admin' | 'superadmin'): boolean {
  const user = getUser();
  if (!user) return false;
  
  const userRole = user.role?.type?.toLowerCase();
  
  if (role === 'researcher') {
    return ['researcher', 'developer', 'admin', 'superadmin'].includes(userRole);
  }
  if (role === 'developer') {
    return ['developer', 'admin', 'superadmin'].includes(userRole);
  }
  if (role === 'admin') {
    return ['admin', 'superadmin'].includes(userRole);
  }
  return userRole === 'superadmin';
}

/**
 * Make authenticated request to the backend API (Haystack).
 */
async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };
  
  if (token) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  }
  
  const response = await fetch(`${API_URL}${API_PREFIX}${endpoint}`, {
    ...options,
    headers,
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: null, message: null }));
    let msg = 'Request failed';
    if (error) {
      if (typeof error.detail === 'string') msg = error.detail;
      else if (Array.isArray(error.detail) && error.detail[0]?.msg) msg = error.detail.map((d: { msg?: string }) => d.msg).join('; ');
      else if (error.error?.message || error.message) msg = error.error?.message || error.message;
    }
    throw new Error(msg);
  }
  
  return response.json();
}

/**
 * Same-origin proxy to Haystack (server uses BACKEND_URL). Use for API keys so create/list
 * always hit the same database as login and query-stream — not whatever NEXT_PUBLIC_API_URL
 * was at build time.
 */
async function fetchApiKeysProxy<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };
  if (token) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  }
  const response = await fetch(`/api/api-keys${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: null, message: null }));
    let msg = 'Request failed';
    if (error) {
      if (typeof error.detail === 'string') msg = error.detail;
      else if (Array.isArray(error.detail) && error.detail[0]?.msg)
        msg = error.detail.map((d: { msg?: string }) => d.msg).join('; ');
      else if (error.error?.message || error.message) msg = error.error?.message || error.message;
    }
    throw new Error(msg);
  }

  return response.json();
}

// ==================== Authentication ====================

const LOGIN_TIMEOUT_MS = 15000;

/**
 * Login via same-origin proxy (/api/auth/login) so the backend URL is only needed server-side.
 * Avoids CORS and wrong NEXT_PUBLIC_API_URL; Next.js route proxies to BACKEND_URL/v1/api/auth/local.
 */
export async function login(credentials: LoginCredentials): Promise<AuthResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), LOGIN_TIMEOUT_MS);
  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(credentials),
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const msg = typeof data?.detail === 'string' ? data.detail : (response.status === 502 ? 'Backend no disponible.' : 'Invalid identifier or password');
      throw new Error(msg);
    }
    storeAuth(data.jwt, data.user);
    return data as AuthResponse;
  } catch (err) {
    clearTimeout(timeoutId);
    if (err instanceof Error) {
      if (err.name === 'AbortError') throw new Error('El servidor no respondió a tiempo. Comprueba que api.ominis.org esté activo y que el frontend tenga BACKEND_URL configurado.');
      throw err;
    }
    throw err;
  }
}

/**
 * Register a new user
 */
export async function register(data: RegisterData): Promise<AuthResponse> {
  const response = await fetchApi<AuthResponse>('/api/auth/local/register', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  
  storeAuth(response.jwt, response.user);
  return response;
}

/**
 * Get Google OAuth redirect URL
 * Redirect user to this URL to initiate Google sign-in
 */
export function getGoogleAuthUrl(): string {
  const base = API_URL.replace(/\/$/, '');
  return `${base}${API_PREFIX}/api/connect/google`;
}

/**
 * Logout the current user
 */
export function logout(): void {
  clearAuth();
}

/**
 * Get current user profile
 */
export async function getProfile(): Promise<User> {
  const response = await fetchApi<User>('/api/users/me?populate=role');
  
  // Update stored user
  const token = getToken();
  if (token) {
    storeAuth(token, response);
  }
  
  return response;
}

/**
 * Update user profile
 */
export async function updateProfile(data: Partial<User>): Promise<User> {
  const user = getUser();
  if (!user) throw new Error('Not authenticated');
  
  const updated = await fetchApi<User>(`/api/users/${user.id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
  
  const token = getToken();
  if (token) {
    storeAuth(token, updated);
  }
  
  return updated;
}

/**
 * Change password
 */
export async function changePassword(
  currentPassword: string,
  newPassword: string
): Promise<void> {
  await fetchApi<void>('/api/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({
      currentPassword,
      password: newPassword,
      passwordConfirmation: newPassword,
    }),
  });
}

/**
 * Request password reset email
 */
export async function forgotPassword(email: string): Promise<{ ok: boolean }> {
  await fetchApi<{ ok: boolean }>('/api/auth/forgot-password', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
  return { ok: true };
}

/**
 * Request password reset via SMS (requires Twilio)
 */
export async function forgotPasswordPhone(phone: string): Promise<{ ok: boolean }> {
  await fetchApi<{ ok: boolean }>('/api/auth/forgot-password-phone', {
    method: 'POST',
    body: JSON.stringify({ phone }),
  });
  return { ok: true };
}

/**
 * Reset password with code from email
 */
export async function resetPassword(
  code: string,
  password: string,
  passwordConfirmation: string
): Promise<AuthResponse> {
  const response = await fetchApi<AuthResponse>('/api/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify({
      code,
      password,
      passwordConfirmation,
    }),
  });
  
  storeAuth(response.jwt, response.user);
  return response;
}

// ==================== API Keys ====================

/**
 * Get user's API keys
 */
export async function getApiKeys(): Promise<ApiKey[]> {
  const response = await fetchApiKeysProxy<{ data: ApiKey[] }>('?populate=owner');
  return response.data;
}

/**
 * Create a new API key
 */
export async function createApiKey(data: CreateApiKeyData): Promise<CreateApiKeyResponse> {
  return fetchApiKeysProxy<CreateApiKeyResponse>('', {
    method: 'POST',
    body: JSON.stringify({ data }),
  });
}

/**
 * Revoke an API key
 */
export async function revokeApiKey(id: number): Promise<void> {
  await fetchApiKeysProxy<void>(`/${id}/revoke`, {
    method: 'POST',
    body: '{}',
  });
}

/**
 * Get API key usage stats
 */
export async function getApiKeyUsage(id: number): Promise<{
  id: number;
  name: string;
  requestsCount: string;
  lastUsedAt?: string;
  rateLimit: number;
  rateLimitWindow: string;
  status: string;
}> {
  return fetchApiKeysProxy(`/${id}/usage`);
}

/**
 * Last 5 request/response bodies logged for this API key (non-streaming captures full JSON; streams get a note).
 */
export async function getApiKeyRecentRequests(id: number): Promise<ApiKeyRecentRequest[]> {
  const response = await fetchApiKeysProxy<{ data: ApiKeyRecentRequest[] }>(`/${id}/recent-requests`, {
    method: 'GET',
  });
  return Array.isArray(response.data) ? response.data : [];
}

// ==================== RAG Sources (Admin+) ====================

/**
 * Get all RAG sources with optional filters
 */
export async function getRagSources(params?: {
  page?: number;
  pageSize?: number;
  status?: string;
  sourceType?: string;
  search?: string;
  taxonomy?: TaxonomyDict;
}): Promise<{ data: RagSource[]; meta: { pagination: { total: number; page: number; pageSize: number } } }> {
  const query = new URLSearchParams();
  if (params?.page) query.set('pagination[page]', String(params.page));
  if (params?.pageSize) query.set('pagination[pageSize]', String(params.pageSize));
  if (params?.status) query.set('filters[status]', params.status);
  if (params?.sourceType) query.set('filters[sourceType]', params.sourceType);
  if (params?.search?.trim()) query.set('filters[search]', params.search.trim());
  if (params?.taxonomy && Object.keys(params.taxonomy).length > 0) {
    query.set('filters[taxonomy]', JSON.stringify(params.taxonomy));
  }
  return fetchApi(`/api/rag-sources?${query.toString()}`);
}

/**
 * Get taxonomy schema (dimensions and valid values)
 */
export async function getTaxonomySchema(): Promise<{ taxonomy: Record<string, string[]> }> {
  return fetchApi('/api/rag-sources/taxonomy-schema');
}

/**
 * Get taxonomy stats (counts by institucion, tipo_documento)
 */
export async function getTaxonomyStats(): Promise<{
  taxonomyStats: Record<string, Record<string, number>>;
}> {
  return fetchApi('/api/rag-sources/taxonomy-stats');
}

/**
 * Run LLM classification for a single source
 */
export async function classifySource(id: number): Promise<{ data: RagSource; message: string }> {
  return fetchApi(`/api/rag-sources/${id}/classify`, { method: 'POST' });
}

/**
 * Batch reindex sources (optionally only those with taxonomy)
 */
export async function batchReindex(options?: {
  onlyWithTaxonomy?: boolean;
  maxConcurrent?: number;
}): Promise<{ message: string; totalQueued: number }> {
  return fetchApi('/api/rag-sources/batch-reindex', {
    method: 'POST',
    body: JSON.stringify({
      onlyWithTaxonomy: options?.onlyWithTaxonomy ?? true,
      maxConcurrent: options?.maxConcurrent ?? 2,
    }),
  });
}

/**
 * Get a single RAG source
 */
export async function getRagSource(id: number): Promise<{ data: RagSource }> {
  return fetchApi(`/api/rag-sources/${id}`);
}

/**
 * Create a new RAG source
 */
export async function createRagSource(data: Partial<RagSource>): Promise<{ data: RagSource }> {
  return fetchApi('/api/rag-sources', {
    method: 'POST',
    body: JSON.stringify({ data }),
  });
}

/**
 * Create multiple RAG sources from URLs; optional crawl (follow same-domain links).
 */
export async function createRagSourcesBatch(params: {
  urls: string[];
  crawl?: boolean;
  category?: string;
}): Promise<{ queued: number; message: string }> {
  return fetchApi('/api/rag-sources/urls-batch', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

/**
 * Update a RAG source
 */
export async function updateRagSource(id: number, data: Partial<RagSource>): Promise<{ data: RagSource }> {
  return fetchApi(`/api/rag-sources/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ data }),
  });
}

/**
 * Delete a RAG source
 */
export async function deleteRagSource(id: number): Promise<void> {
  await fetchApi(`/api/rag-sources/${id}`, {
    method: 'DELETE',
  });
}

/**
 * Mark sources stuck in "indexing" (no update for older_than_minutes) as error so they can be retried.
 */
export async function markStuckIndexingAsFailed(
  olderThanMinutes: number = 30,
): Promise<{
  promoted: number;
  markedError: number;
  olderThanMinutes: number;
  checked: number;
}> {
  return fetchApi(
    `/api/rag-sources/mark-stuck-indexing?older_than_minutes=${encodeURIComponent(olderThanMinutes)}`,
    { method: 'POST' },
  );
}

/**
 * Set status to active when pgvector already has chunks (fixes false "error" rows).
 */
export async function reconcileRagSourceStatus(
  includeIndexing: boolean = false,
  includeActive: boolean = true,
): Promise<{ fixed: number; syncedCounts: number; checked: number }> {
  return fetchApi(
    `/api/rag-sources/reconcile-status?include_indexing=${includeIndexing ? 'true' : 'false'}&include_active=${includeActive ? 'true' : 'false'}`,
    { method: 'POST' },
  );
}

/**
 * Trigger re-indexing of a source
 */
export async function reindexSource(id: number): Promise<{ message: string; sourceId: number; status: string }> {
  return fetchApi(`/api/rag-sources/${id}/reindex`, {
    method: 'POST',
  });
}

/**
 * Get RAG source statistics
 */
export async function getSourceStats(): Promise<{
  total: number;
  byStatus: {
    indexed: number;
    pending: number;
    processing: number;
    failed: number;
  };
  totalChunks: number;
}> {
  return fetchApi('/api/rag-sources/stats');
}

/**
 * Upload a file as a RAG source
 */
export async function uploadRagFile(
  file: File,
  metadata: { title: string; category?: string; language?: string }
): Promise<{ message: string; sourceId: number; chunksCount: number; status: string }> {
  const token = getToken();
  const formData = new FormData();
  formData.append('file', file);
  formData.append('title', metadata.title);
  if (metadata.category) formData.append('category', metadata.category);
  formData.append('language', metadata.language || 'es');

  const response = await fetch(`${API_URL}${API_PREFIX}/api/rag-sources/upload`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });

  if (!response.ok) {
    if (response.status === 413) {
      throw new Error('File too large. Maximum size is 50MB. If the server was recently set up, ask the admin to run infrastructure/20g-backend-nginx-upload-size.sh.');
    }
    const err = await response.json().catch(() => ({ detail: 'Upload failed' }));
    const msg = typeof err.detail === 'string' ? err.detail : Array.isArray(err.detail) ? (err.detail as { msg?: string }[]).map((x) => x?.msg).filter(Boolean).join('; ') : null;
    throw new Error(msg || `Upload failed: ${response.status}`);
  }

  return response.json();
}

/**
 * Get chunks belonging to a specific source
 */
export async function getSourceChunks(
  sourceId: number,
  page: number = 1,
  pageSize: number = 20
): Promise<{
  data: Array<{
    id: string;
    contentPreview: string;
    title?: string;
    url?: string;
    sourceType?: string;
    sourceId?: number;
  }>;
  meta: { pagination: { total: number; page: number; pageSize: number } };
}> {
  return fetchApi(`/api/rag-sources/${sourceId}/chunks?page=${page}&page_size=${pageSize}`);
}

/**
 * Get document store statistics
 */
export async function getStoreStats(): Promise<{
  totalDocuments: number;
  embeddingModel: string;
  embeddingDimension: number;
  storageType: string;
}> {
  return fetchApi('/api/rag-sources/store-stats');
}

/**
 * Health datastore (nightly Mexican health ingestion) status: doc/chunk counts and retrieval test.
 */
export async function getHealthDatastoreStatus(): Promise<{
  enabled: boolean;
  health_docs: number;
  health_chunks: number;
  evidence_pack_test_count: number;
  opensearch_url_set?: boolean;
  error?: string;
}> {
  return fetchApi('/health-datastore/status');
}

/**
 * Health datastore recent ingestion activity (last N docs with URL, source type, date).
 */
export async function getHealthDatastoreRecentActivity(limit = 20): Promise<{
  items: Array<{ title: string; source_url: string; source_type: string; date_ingested: string | null }>;
  error?: string;
  note?: string;
}> {
  return fetchApi(`/health-datastore/recent-activity?limit=${limit}`);
}

/** Admin/developer: ingested doctor directory stats (Mexico listings). */
export async function getDoctorDirectoryStats(): Promise<{
  total_profiles: number;
  by_source: Record<string, number>;
  last_scraped_at: string | null;
}> {
  return fetchApi('/api/doctor-directory/stats');
}

export type DoctorDirectoryScrapeRun = {
  id: number;
  source_site: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  max_profiles: number;
  profiles_attempted: number;
  profiles_upserted: number;
  profiles_failed: number;
  error_message: string | null;
  created_at: string;
};

export async function getDoctorDirectoryRuns(limit = 25): Promise<DoctorDirectoryScrapeRun[]> {
  return fetchApi(`/api/doctor-directory/runs?limit=${limit}`);
}

export async function startDoctorDirectoryScrape(body: {
  source?: 'topdoctors_mx' | 'doctoralia_mx' | 'doctoranytime_mx' | string;
  max_profiles?: number;
  delay_seconds?: number;
}): Promise<{ run_id: number; message: string }> {
  return fetchApi('/api/doctor-directory/scrape', {
    method: 'POST',
    body: JSON.stringify({
      source: body.source ?? 'topdoctors_mx',
      max_profiles: body.max_profiles ?? 50,
      delay_seconds: body.delay_seconds ?? 0.6,
    }),
  });
}

/**
 * Admin/developer: download full doctor_directory_profiles table as CSV (browser download).
 */
export async function downloadDoctorDirectoryCsv(): Promise<void> {
  const token = getToken();
  const response = await fetch(`${API_URL}${API_PREFIX}/api/doctor-directory/export.csv`, {
    method: 'GET',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: null, message: null }));
    let msg = 'Export failed';
    if (error && typeof error === 'object') {
      const e = error as { detail?: unknown; message?: string };
      if (typeof e.detail === 'string') msg = e.detail;
      else if (Array.isArray(e.detail) && e.detail[0]?.msg) msg = e.detail.map((d: { msg?: string }) => d.msg).join('; ');
      else if (e.message) msg = e.message;
    }
    throw new Error(msg);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `doctor_directory_mexico_${new Date().toISOString().slice(0, 10)}.csv`;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Preview: scrape a URL for PDF, CSV, XLS, XLSX links without indexing
 */
export async function scrapePreview(url: string): Promise<{
  url: string;
  totalPdfs: number;
  pdfs: Array<{ title: string; pdfUrl: string; sourcePage: string }>;
  totalFiles: number;
  files: Array<{ title: string; fileUrl: string; sourcePage: string; format: string }>;
}> {
  return fetchApi('/api/rag-sources/scrape-preview', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

/**
 * Scrape files (PDF, CSV, XLS, XLSX) from a URL and index selected
 */
export async function scrapeAndIndex(
  url: string,
  options?: {
    category?: string;
    language?: string;
    pdfs?: Array<{ title: string; pdfUrl: string; sourcePage: string }>;
    files?: Array<{ title: string; fileUrl: string; sourcePage: string; format: string }>;
  }
): Promise<{
  message: string;
  totalQueued: number;
  sources: Array<{ sourceId: number; title: string; pdfUrl: string; fileUrl?: string; format?: string; status: string }>;
}> {
  return fetchApi('/api/rag-sources/scrape-index', {
    method: 'POST',
    body: JSON.stringify({
      url,
      category: options?.category || '',
      language: options?.language || 'es',
      pdfs: options?.pdfs || null,
      files: options?.files || null,
    }),
  });
}

// ==================== Dataset Import (Admin+) ====================

/**
 * Preview dataset page resources (CSV, XLS, PDF from data portals)
 */
export async function datasetPreview(url: string): Promise<{
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
  }>;
}> {
  return fetchApi('/api/rag-sources/dataset-preview', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

/**
 * Index resources from a dataset page
 */
export async function datasetIndex(
  url: string,
  options?: {
    category?: string;
    language?: string;
    pageTitle?: string;
    pageMetadata?: Record<string, string>;
    resources?: Array<{
      title: string;
      description: string;
      url: string;
      format: string;
      resourceId: string;
      sourcePage: string;
    }>;
  }
): Promise<{
  message: string;
  totalQueued: number;
  sources: Array<{ sourceId: number; title: string; url: string; format: string; status: string }>;
}> {
  return fetchApi('/api/rag-sources/dataset-index', {
    method: 'POST',
    body: JSON.stringify({
      url,
      category: options?.category || '',
      language: options?.language || 'es',
      pageTitle: options?.pageTitle || '',
      pageMetadata: options?.pageMetadata || {},
      resources: options?.resources || null,
    }),
  });
}

// ==================== Tainacan Import (Admin+) ====================

/**
 * Preview Tainacan collection items
 */
export async function tainacanPreview(): Promise<{
  totalItems: number;
  indexableFiles: number;
  metadataOnly: number;
  byExtension: Record<string, number>;
}> {
  return fetchApi('/api/rag-sources/tainacan-preview');
}

/**
 * Import all items from Tainacan collection
 */
export async function tainacanImport(options?: {
  category?: string;
  language?: string;
  maxItems?: number;
  skipExisting?: boolean;
}): Promise<{
  message: string;
  totalQueued: number;
  skipped: number;
}> {
  return fetchApi('/api/rag-sources/tainacan-import', {
    method: 'POST',
    body: JSON.stringify({
      category: options?.category || 'tainacan',
      language: options?.language || 'es',
      maxItems: options?.maxItems || null,
      skipExisting: options?.skipExisting !== false,
    }),
  });
}

// ==================== datos.gob.mx CKAN (metadata) ====================

export async function datosGobMxPreview(group?: string): Promise<{
  totalPackages: number;
  groupName: string;
  groupTitle: string;
  totalResourcesSample: number;
  resourceFormatsSample: Record<string, number>;
  sampleTitles: string[];
}> {
  const q = group && group.trim() ? `?group=${encodeURIComponent(group.trim())}` : '';
  return fetchApi(`/api/rag-sources/datos-gob-mx-preview${q}`);
}

export async function datosGobMxImport(options?: {
  category?: string;
  language?: string;
  maxItems?: number | null;
  skipExisting?: boolean;
  group?: string;
}): Promise<{
  message: string;
  totalQueued: number;
  skipped: number;
}> {
  return fetchApi('/api/rag-sources/datos-gob-mx-import', {
    method: 'POST',
    body: JSON.stringify({
      category: options?.category || 'datos.gob.mx',
      language: options?.language || 'es',
      maxItems: options?.maxItems ?? null,
      skipExisting: options?.skipExisting !== false,
      group: options?.group || 'salud',
    }),
  });
}

// ==================== System Stats (Admin+) ====================

/**
 * Get system statistics
 */
export async function getSystemStats(): Promise<{ data: SystemStats }> {
  return fetchApi('/api/system-stats');
}

/** Aggregated overview for Visión general (health checks, servers, queries, sources, users). */
export async function getDashboardOverview(): Promise<{ data: DashboardOverview }> {
  return fetchApi('/api/system-stats/dashboard-overview');
}

/**
 * Time-bucketed query counts for admin dashboard charts.
 * Same-origin /api/... so Next.js proxies to BACKEND_URL (see app/api/system-stats/query-series/route.ts).
 */
export async function getQuerySeries(): Promise<{ data: QuerySeries }> {
  const token = getToken();
  const headers: HeadersInit = { 'Content-Type': 'application/json' };
  if (token) (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;

  const response = await fetch('/api/system-stats/query-series', { headers });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: null as string | null, message: null as string | null }));
    let msg = 'Request failed';
    if (error) {
      if (typeof error.detail === 'string') msg = error.detail;
      else if (Array.isArray(error.detail) && error.detail[0]?.msg)
        msg = error.detail.map((d: { msg?: string }) => d.msg).join('; ');
      else if (error.error?.message || error.message) msg = error.error?.message || error.message;
    }
    throw new Error(msg);
  }
  return response.json();
}

/**
 * Refresh system statistics
 */
export async function refreshSystemStats(): Promise<{ message: string; stats: SystemStats }> {
  return fetchApi('/api/system-stats/refresh', {
    method: 'POST',
  });
}

/**
 * Get server performance metrics (CPU, memory, GPU, workers)
 */
export async function getServerPerformance(): Promise<{
  cpu?: { cores: number; loadAvg1m: number; loadAvg5m: number; loadAvg15m: number; usagePercent: number };
  memory?: { totalMB: number; usedMB: number; availableMB: number; usagePercent: number };
  disk?: { totalGB: number; usedGB: number; freeGB: number; usagePercent: number };
  gpu?: { name: string; memoryTotalMB: number; memoryUsedMB: number; memoryFreeMB: number; utilizationPercent: number; temperatureC: number } | null;
  workers?: Array<{ pid: number; cpuPercent: number; memPercent: number; memMB: number }>;
  database?: { activeConnections: number; idleConnections: number; totalConnections: number } | null;
  uptimeHours?: number;
}> {
  return fetchApi('/api/system-stats/server-performance');
}

/**
 * Get research GPU instance status (Ominis 2.0 Research 8K and 128K)
 * Admin only.
 */
export async function getResearchInstanceStatus(): Promise<{
  openscholar: string | null;
  openscholar_128k: string | null;
  details?: Record<'openscholar' | 'openscholar_128k', InstanceDetails>;
}> {
  return fetchApi('/api/research-instances/status');
}

/**
 * Start a research GPU instance (openscholar | openscholar_128k). 128K auto-stops after 60 min.
 * Admin only.
 */
export async function startResearchInstance(key: 'openscholar' | 'openscholar_128k'): Promise<{ status: string; message: string }> {
  return fetchApi(`/api/research-instances/start?key=${encodeURIComponent(key)}`, { method: 'POST' });
}

/**
 * Stop a research GPU instance. Admin only.
 */
export async function stopResearchInstance(key: 'openscholar' | 'openscholar_128k'): Promise<{ status: string; message: string }> {
  return fetchApi(`/api/research-instances/stop?key=${encodeURIComponent(key)}`, { method: 'POST' });
}

/**
 * Get status of each configured Ollama server and the list of model names on each.
 * Use to verify servers (e.g. BioMistral, Qwen, Falcon) and that config matches reality.
 */
export async function getLlmServersStatus(): Promise<{
  servers: Array<{
    label: string;
    url: string | null;
    reachable: boolean;
    models: string[];
    note?: string;
    error?: string;
  }>;
}> {
  return fetchApi('/api/llm-servers/status');
}

/** Instance details returned for LLM and research instances (dashboard). */
export type InstanceDetails = {
  instanceId: string | null;
  instanceType: string | null;
  publicIp: string | null;
  state: string | null;
  vramGb: number | null;
  ramGb: number | null;
  modelBase: string;
  modelDescription: string;
};

/**
 * Get LLM GPU instance status (ominis-2.0 and optionally ominis-2.0-med). Admin/researcher.
 */
export async function getLlmInstanceStatus(): Promise<{
  'ominis-2.0': string | null;
  'ominis-2.0-med'?: string | null;
  details?: Record<string, InstanceDetails>;
}> {
  return fetchApi('/api/llm-instances/status');
}

/**
 * Start an LLM GPU instance (ominis-2.0 | ominis-2.0-med). Admin only.
 */
export async function startLlmInstance(key: 'ominis-2.0' | 'ominis-2.0-med'): Promise<{ status: string; message: string }> {
  return fetchApi(`/api/llm-instances/start?key=${encodeURIComponent(key)}`, { method: 'POST' });
}

/**
 * Stop an LLM GPU instance (ominis-2.0 | ominis-2.0-med). Admin only.
 */
export async function stopLlmInstance(key: 'ominis-2.0' | 'ominis-2.0-med'): Promise<{ status: string; message: string }> {
  return fetchApi(`/api/llm-instances/stop?key=${encodeURIComponent(key)}`, { method: 'POST' });
}

/** One EC2 server with its instance details and models (for dashboard grouped view). */
export type ServerWithModels = {
  instanceId: string;
  instanceType: string | null;
  publicIp: string | null;
  state: string;
  vramGb: number | null;
  ramGb: number | null;
  /** Approximate on-demand USD/month (24/7) when known */
  estimatedMonthlyUsd?: number | null;
  primaryKey: string;
  primaryKeyType: 'llm' | 'research';
  models: Array<{ key: string; label: string; modelBase: string; modelDescription: string }>;
  isRemote?: boolean;
};

/**
 * Get all LLM servers grouped by EC2 instance (Ominis 2.0 and Ominis 2.0 Med). One on/off per server.
 */
export async function getServersStatus(): Promise<{ servers: ServerWithModels[]; error?: string }> {
  return fetchApi('/api/servers/status');
}

/** LLM model config (dashboard: assignments, prompts, version, params) */
export type LLMModelConfigItem = {
  model_id: string;
  display_name: string;
  version_label: string;
  description: string;
  backend_type: 'ollama' | 'openai' | 'anthropic';
  llm_provider: string;
  provider_keys_present: Record<string, boolean>;
  backend_model: string;
  backend_url_override: string | null;
  system_prompt: string | null;
  temperature: number | null;
  num_predict: number | null;
  extra_params: Record<string, unknown> | null;
  is_default: boolean;
  overridden: string[];
  available_for_researcher?: boolean;
};

export type LlmProviderOption = { id: string; label: string; credential_key: string };

export async function getLLMModelProviders(): Promise<{ providers: LlmProviderOption[] }> {
  return fetchApi('/api/llm-models/providers');
}

export async function postLLMListModels(body: {
  model_id: string;
  provider_id: string;
  api_token?: string;
}): Promise<{ models: string[] }> {
  return fetchApi('/api/llm-models/list-models', { method: 'POST', body: JSON.stringify(body) });
}

export type VisionLlmConfig = {
  llm_provider: string;
  backend_model: string;
  ollama_url: string;
  openai_base_url: string;
  provider_keys_present: Record<string, boolean>;
};

export async function getVisionLlmConfig(): Promise<VisionLlmConfig> {
  return fetchApi('/api/vision-llm-config');
}

export async function putVisionLlmConfig(
  body: Partial<{
    llm_provider: string;
    backend_model: string;
    ollama_url: string;
    openai_base_url: string;
    provider_credentials_patch: Record<string, string>;
  }>
): Promise<VisionLlmConfig> {
  return fetchApi('/api/vision-llm-config', { method: 'PUT', body: JSON.stringify(body) });
}

export async function getLLMModelsConfig(): Promise<LLMModelConfigItem[]> {
  return fetchApi('/api/llm-models/config');
}

export async function updateLLMModelConfig(
  modelId: string,
  body: Partial<{
    display_name: string;
    version_label: string;
    description: string;
    backend_model: string;
    backend_url_override: string;
    system_prompt: string;
    temperature: number;
    num_predict: number;
    extra_params: Record<string, unknown>;
    is_default: boolean;
    available_for_researcher: boolean;
    llm_provider: string;
    provider_credentials_patch: Record<string, string>;
  }>
): Promise<{ status: string; model_id: string }> {
  return fetchApi(`/api/llm-models/config/${encodeURIComponent(modelId)}`, { method: 'PUT', body: JSON.stringify(body) });
}

/**
 * Get default chat toggles (Investigación, Ominis, PubMed, Web). Public — used when the chat loads.
 */
export async function getChatDefaults(): Promise<{
  research_mode: boolean;
  rag_search: boolean;
  web_search: boolean;
  pubmed_search: boolean;
  openscholar_search: boolean;
  research_2_1: boolean;
  public_access_enabled: boolean;
  default_model?: string;
}> {
  return fetchApi('/api/chat-defaults');
}

/**
 * Update default chat toggles. Admin only.
 */
export async function updateChatDefaults(defaults: {
  research_mode?: boolean;
  rag_search?: boolean;
  web_search?: boolean;
  pubmed_search?: boolean;
  openscholar_search?: boolean;
  research_2_1?: boolean;
  public_access_enabled?: boolean;
  default_model?: string;
}): Promise<{
  research_mode: boolean;
  rag_search: boolean;
  web_search: boolean;
  pubmed_search: boolean;
  openscholar_search: boolean;
  research_2_1: boolean;
  public_access_enabled: boolean;
  default_model?: string;
}> {
  return fetchApi('/api/chat-defaults', {
    method: 'PATCH',
    body: JSON.stringify(defaults),
  });
}

/**
 * Get site config (e.g. global banner message). Public — used to show notification at top of app.
 */
export async function getSiteConfig(): Promise<{ banner_message: string | null }> {
  return fetchApi('/api/site-config');
}

/**
 * Update site config (e.g. global banner). Superadmin only.
 */
export async function updateSiteConfig(config: { banner_message?: string | null }): Promise<{ banner_message: string | null }> {
  return fetchApi('/api/site-config', {
    method: 'PATCH',
    body: JSON.stringify(config),
  });
}

/**
 * Get GPU/LLM server performance metrics
 */
export async function getGpuServerPerformance(): Promise<{
  status: string;
  ollamaUrl?: string;
  ollamaVersion?: string;
  gpuServerIp?: string;
  models?: Array<{ name: string; sizeGB: number; parameterSize: string; quantization: string }>;
  runningModels?: Array<{ name: string; sizeVramGB: number }>;
  inference?: { latencyMs: number; tokensPerSecond: number; evalCount: number; evalDurationMs: number; loadDurationMs: number };
  error?: string;
}> {
  return fetchApi('/api/system-stats/gpu-server');
}

/**
 * Get system health (public endpoint)
 */
/**
 * Get system health (public endpoint)
 * Note: This endpoint doesn't use the /v1 prefix
 */
export async function getHealth(): Promise<HealthSnapshot> {
  const response = await fetch(`${API_URL}${API_PREFIX}/system-stats/health`);
  return response.json();
}

// ==================== Query Logs (Admin+) ====================

/**
 * Get aggregated query statistics
 */
export async function getQueryStats(period: 'hour' | 'day' | 'week' | 'month' = 'day'): Promise<QueryStats> {
  return fetchApi(`/api/query-logs/aggregated?period=${period}`);
}

/**
 * Get usage stats for the current user
 */
export async function getUserUsage(period: 'day' | 'week' | 'month' = 'month'): Promise<UserUsage> {
  return fetchApi(`/api/users/me/usage?period=${period}`);
}

// ==================== User Management (SuperAdmin) ====================

/**
 * Get all users (SuperAdmin only)
 */
export async function getUsers(): Promise<User[]> {
  return fetchApi('/api/users?populate=role');
}

/**
 * Update a user (SuperAdmin only)
 */
export async function updateUser(id: number, data: Partial<User>): Promise<User> {
  return fetchApi(`/api/users/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

/**
 * Block/unblock a user (SuperAdmin only)
 */
export async function toggleUserBlock(id: number, blocked: boolean): Promise<User> {
  return fetchApi(`/api/users/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ blocked }),
  });
}

/**
 * Delete a user (SuperAdmin only)
 */
export async function deleteUser(id: number): Promise<void> {
  await fetchApi(`/api/users/${id}`, {
    method: 'DELETE',
  });
}
