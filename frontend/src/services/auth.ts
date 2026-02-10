/**
 * Authentication Service for Ominis Health
 * Handles user authentication, API key management, and admin functions
 */

import type {
  User,
  AuthResponse,
  LoginCredentials,
  RegisterData,
  ApiKey,
  CreateApiKeyData,
  CreateApiKeyResponse,
  RagSource,
  SystemStats,
  QueryStats,
  UserUsage,
  TaxonomyDict,
} from '@/types/auth';

// Configuration - Backend API URL
// Supports both the new Haystack backend and legacy Strapi backend
const STRAPI_URL = process.env.NEXT_PUBLIC_STRAPI_URL || 'http://localhost:8000';
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
 * Make authenticated request to Strapi
 */
async function fetchStrapi<T>(
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
  
  const response = await fetch(`${STRAPI_URL}${API_PREFIX}${endpoint}`, {
    ...options,
    headers,
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Request failed' }));
    throw new Error(error.error?.message || error.message || 'Request failed');
  }
  
  return response.json();
}

// ==================== Authentication ====================

/**
 * Login with email/username and password
 */
export async function login(credentials: LoginCredentials): Promise<AuthResponse> {
  const response = await fetchStrapi<AuthResponse>('/api/auth/local', {
    method: 'POST',
    body: JSON.stringify(credentials),
  });
  
  storeAuth(response.jwt, response.user);
  return response;
}

/**
 * Register a new user
 */
export async function register(data: RegisterData): Promise<AuthResponse> {
  const response = await fetchStrapi<AuthResponse>('/api/auth/local/register', {
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
  const base = STRAPI_URL.replace(/\/$/, '');
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
  const response = await fetchStrapi<User>('/api/users/me?populate=role');
  
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
  
  const updated = await fetchStrapi<User>(`/api/users/${user.id}`, {
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
  await fetchStrapi<void>('/api/auth/change-password', {
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
  await fetchStrapi<{ ok: boolean }>('/api/auth/forgot-password', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
  return { ok: true };
}

/**
 * Request password reset via SMS (requires Twilio)
 */
export async function forgotPasswordPhone(phone: string): Promise<{ ok: boolean }> {
  await fetchStrapi<{ ok: boolean }>('/api/auth/forgot-password-phone', {
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
  const response = await fetchStrapi<AuthResponse>('/api/auth/reset-password', {
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
  const response = await fetchStrapi<{ data: ApiKey[] }>('/api/api-keys?populate=owner');
  return response.data;
}

/**
 * Create a new API key
 */
export async function createApiKey(data: CreateApiKeyData): Promise<CreateApiKeyResponse> {
  return fetchStrapi<CreateApiKeyResponse>('/api/api-keys', {
    method: 'POST',
    body: JSON.stringify({ data }),
  });
}

/**
 * Revoke an API key
 */
export async function revokeApiKey(id: number): Promise<void> {
  await fetchStrapi<void>(`/api/api-keys/${id}/revoke`, {
    method: 'POST',
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
  return fetchStrapi(`/api/api-keys/${id}/usage`);
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
  return fetchStrapi(`/api/rag-sources?${query.toString()}`);
}

/**
 * Get taxonomy schema (dimensions and valid values)
 */
export async function getTaxonomySchema(): Promise<{ taxonomy: Record<string, string[]> }> {
  return fetchStrapi('/api/rag-sources/taxonomy-schema');
}

/**
 * Get taxonomy stats (counts by institucion, tipo_documento)
 */
export async function getTaxonomyStats(): Promise<{
  taxonomyStats: Record<string, Record<string, number>>;
}> {
  return fetchStrapi('/api/rag-sources/taxonomy-stats');
}

/**
 * Run LLM classification for a single source
 */
export async function classifySource(id: number): Promise<{ data: RagSource; message: string }> {
  return fetchStrapi(`/api/rag-sources/${id}/classify`, { method: 'POST' });
}

/**
 * Batch reindex sources (optionally only those with taxonomy)
 */
export async function batchReindex(options?: {
  onlyWithTaxonomy?: boolean;
  maxConcurrent?: number;
}): Promise<{ message: string; totalQueued: number }> {
  return fetchStrapi('/api/rag-sources/batch-reindex', {
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
  return fetchStrapi(`/api/rag-sources/${id}`);
}

/**
 * Create a new RAG source
 */
export async function createRagSource(data: Partial<RagSource>): Promise<{ data: RagSource }> {
  return fetchStrapi('/api/rag-sources', {
    method: 'POST',
    body: JSON.stringify({ data }),
  });
}

/**
 * Update a RAG source
 */
export async function updateRagSource(id: number, data: Partial<RagSource>): Promise<{ data: RagSource }> {
  return fetchStrapi(`/api/rag-sources/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ data }),
  });
}

/**
 * Delete a RAG source
 */
export async function deleteRagSource(id: number): Promise<void> {
  await fetchStrapi(`/api/rag-sources/${id}`, {
    method: 'DELETE',
  });
}

/**
 * Trigger re-indexing of a source
 */
export async function reindexSource(id: number): Promise<{ message: string; sourceId: number; status: string }> {
  return fetchStrapi(`/api/rag-sources/${id}/reindex`, {
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
  return fetchStrapi('/api/rag-sources/stats');
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

  const response = await fetch(`${STRAPI_URL}${API_PREFIX}/api/rag-sources/upload`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(err.detail || `Upload failed: ${response.status}`);
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
  return fetchStrapi(`/api/rag-sources/${sourceId}/chunks?page=${page}&page_size=${pageSize}`);
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
  return fetchStrapi('/api/rag-sources/store-stats');
}

/**
 * Preview: scrape a URL for PDF links without indexing
 */
export async function scrapePreview(url: string): Promise<{
  url: string;
  totalPdfs: number;
  pdfs: Array<{ title: string; pdfUrl: string; sourcePage: string }>;
}> {
  return fetchStrapi('/api/rag-sources/scrape-preview', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

/**
 * Scrape PDFs from a URL and index them all
 */
export async function scrapeAndIndex(
  url: string,
  options?: {
    category?: string;
    language?: string;
    pdfs?: Array<{ title: string; pdfUrl: string; sourcePage: string }>;
  }
): Promise<{
  message: string;
  totalQueued: number;
  sources: Array<{ sourceId: number; title: string; pdfUrl: string; status: string }>;
}> {
  return fetchStrapi('/api/rag-sources/scrape-index', {
    method: 'POST',
    body: JSON.stringify({
      url,
      category: options?.category || '',
      language: options?.language || 'es',
      pdfs: options?.pdfs || null,
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
  return fetchStrapi('/api/rag-sources/dataset-preview', {
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
  return fetchStrapi('/api/rag-sources/dataset-index', {
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
  return fetchStrapi('/api/rag-sources/tainacan-preview');
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
  return fetchStrapi('/api/rag-sources/tainacan-import', {
    method: 'POST',
    body: JSON.stringify({
      category: options?.category || 'tainacan',
      language: options?.language || 'es',
      maxItems: options?.maxItems || null,
      skipExisting: options?.skipExisting !== false,
    }),
  });
}

// ==================== System Stats (Admin+) ====================

/**
 * Get system statistics
 */
export async function getSystemStats(): Promise<{ data: SystemStats }> {
  return fetchStrapi('/api/system-stats');
}

/**
 * Refresh system statistics
 */
export async function refreshSystemStats(): Promise<{ message: string; stats: SystemStats }> {
  return fetchStrapi('/api/system-stats/refresh', {
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
  return fetchStrapi('/api/system-stats/server-performance');
}

/**
 * Get research GPU instance status (OpenScholar 8K and 128K)
 * Admin only.
 */
export async function getResearchInstanceStatus(): Promise<{
  openscholar: string | null;
  openscholar_128k: string | null;
}> {
  return fetchStrapi('/api/research-instances/status');
}

/**
 * Start a research GPU instance (openscholar | openscholar_128k). 128K auto-stops after 60 min.
 * Admin only.
 */
export async function startResearchInstance(key: 'openscholar' | 'openscholar_128k'): Promise<{ status: string; message: string }> {
  return fetchStrapi(`/api/research-instances/start?key=${encodeURIComponent(key)}`, { method: 'POST' });
}

/**
 * Stop a research GPU instance. Admin only.
 */
export async function stopResearchInstance(key: 'openscholar' | 'openscholar_128k'): Promise<{ status: string; message: string }> {
  return fetchStrapi(`/api/research-instances/stop?key=${encodeURIComponent(key)}`, { method: 'POST' });
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
  return fetchStrapi('/api/system-stats/gpu-server');
}

/**
 * Get system health (public endpoint)
 */
/**
 * Get system health (public endpoint)
 * Note: This endpoint doesn't use the /v1 prefix
 */
export async function getHealth(): Promise<{
  status: string;
  timestamp: string;
  model: { version: string; status: string };
  servers: { cpu: string; gpu: string };
  lastCheck?: string;
}> {
  const response = await fetch(`${STRAPI_URL}${API_PREFIX}/system-stats/health`);
  return response.json();
}

// ==================== Query Logs (Admin+) ====================

/**
 * Get aggregated query statistics
 */
export async function getQueryStats(period: 'hour' | 'day' | 'week' | 'month' = 'day'): Promise<QueryStats> {
  return fetchStrapi(`/api/query-logs/aggregated?period=${period}`);
}

/**
 * Get usage stats for the current user
 */
export async function getUserUsage(period: 'day' | 'week' | 'month' = 'month'): Promise<UserUsage> {
  return fetchStrapi(`/api/users/me/usage?period=${period}`);
}

// ==================== User Management (SuperAdmin) ====================

/**
 * Get all users (SuperAdmin only)
 */
export async function getUsers(): Promise<User[]> {
  return fetchStrapi('/api/users?populate=role');
}

/**
 * Update a user (SuperAdmin only)
 */
export async function updateUser(id: number, data: Partial<User>): Promise<User> {
  return fetchStrapi(`/api/users/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

/**
 * Block/unblock a user (SuperAdmin only)
 */
export async function toggleUserBlock(id: number, blocked: boolean): Promise<User> {
  return fetchStrapi(`/api/users/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ blocked }),
  });
}

/**
 * Delete a user (SuperAdmin only)
 */
export async function deleteUser(id: number): Promise<void> {
  await fetchStrapi(`/api/users/${id}`, {
    method: 'DELETE',
  });
}
