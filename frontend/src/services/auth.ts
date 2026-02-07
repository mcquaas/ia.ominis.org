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
 * Store authentication data
 */
function storeAuth(jwt: string, user: User): void {
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
export function hasRole(role: 'researcher' | 'admin' | 'superadmin'): boolean {
  const user = getUser();
  if (!user) return false;
  
  const userRole = user.role?.type?.toLowerCase();
  
  if (role === 'researcher') {
    return ['researcher', 'admin', 'superadmin'].includes(userRole);
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
  
  return fetchStrapi<User>(`/api/users/${user.id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
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
 * Get all RAG sources
 */
export async function getRagSources(params?: {
  page?: number;
  pageSize?: number;
  status?: string;
  sourceType?: string;
}): Promise<{ data: RagSource[]; meta: { pagination: { total: number } } }> {
  const query = new URLSearchParams();
  if (params?.page) query.set('pagination[page]', String(params.page));
  if (params?.pageSize) query.set('pagination[pageSize]', String(params.pageSize));
  if (params?.status) query.set('filters[status]', params.status);
  if (params?.sourceType) query.set('filters[sourceType]', params.sourceType);
  
  return fetchStrapi(`/api/rag-sources?${query.toString()}`);
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
