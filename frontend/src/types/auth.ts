/**
 * Authentication types for Ominis Health
 */

export interface User {
  id: number;
  username: string;
  email: string;
  phone?: string | null;
  phoneVerified?: boolean;
  emailVerified?: boolean;
  role: {
    id: number;
    name: string;
    type: string;
  };
  full_name?: string | null;
  institution?: string | null;
  bio?: string | null;
  confirmed: boolean;
  blocked: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface AuthResponse {
  jwt: string;
  user: User;
}

export interface LoginCredentials {
  identifier: string; // email or username
  password: string;
}

export interface RegisterData {
  username: string;
  email: string;
  phone?: string;
  password: string;
}

export interface ApiKey {
  id: number;
  name: string;
  description?: string;
  keyPrefix: string;
  status: 'active' | 'inactive' | 'revoked' | 'expired';
  permissions: {
    query: boolean;
    queryGpu: boolean;
    sources: boolean;
  };
  rateLimit: number;
  rateLimitWindow: 'minute' | 'hour' | 'day';
  requestsCount: string;
  lastUsedAt?: string;
  expiresAt?: string;
  createdAt: string;
}

export interface CreateApiKeyData {
  name: string;
  description?: string;
  permissions?: {
    query?: boolean;
    queryGpu?: boolean;
    sources?: boolean;
  };
  rateLimit?: number;
  rateLimitWindow?: 'minute' | 'hour' | 'day';
  expiresAt?: string;
}

export interface CreateApiKeyResponse {
  data: ApiKey;
  apiKey: string; // The full API key - only shown once!
  message: string;
}

/** Taxonomy dimension values (e.g. institucion: ["SSA"], tipo_documento: ["guia_clinica"]) */
export type TaxonomyDict = Record<string, string[]>;

export interface RagSource {
  id: number;
  title: string;
  slug: string;
  sourceType: 'tainacan' | 'wordpress' | 'imss_guideline' | 'issste_guideline' | 'pubmed' | 'manual_upload' | 'webpage' | 'text' | 'pdf' | 'docx' | 'txt' | 'html' | 'other';
  status: 'pending' | 'processing' | 'indexed' | 'failed' | 'archived' | 'active' | 'indexing' | 'error';
  content?: string;
  sourceUrl?: string;
  externalId?: string;
  metadata?: Record<string, unknown>;
  description?: string;
  publisher?: string;
  documentDate?: string;
  taxonomy?: TaxonomyDict;
  chunksCount: number;
  lastIndexedAt?: string;
  indexingError?: string;
  category: string;
  language: 'es' | 'en' | 'es-mx';
  qualityScore?: number;
  notes?: string;
  createdAt: string;
  updatedAt: string;
  publishedAt?: string;
}

export interface SystemStats {
  totalSources: number;
  indexedSources: number;
  totalChunks: number;
  embeddingsSize?: string;
  faissIndexSize?: string;
  lastIndexUpdate?: string;
  modelVersion: string;
  modelStatus: 'online' | 'offline' | 'degraded';
  cpuServerStatus: 'online' | 'offline' | 'degraded';
  gpuServerStatus: 'online' | 'offline' | 'degraded';
  avgResponseTimeCpu?: number;
  avgResponseTimeGpu?: number;
  totalQueries24h: number;
  totalQueriesWeek: number;
  totalQueriesMonth: number;
  errorRate24h: number;
  lastHealthCheck?: string;
}

export interface QueryStats {
  period: string;
  startDate: string;
  endDate: string;
  total: number;
  successful: number;
  failed: number;
  successRate: number;
  avgResponseTimeMs: number;
  totalTokens: number;
  byEndpoint: {
    query: number;
    'query-gpu': number;
  };
}

export interface UserUsage {
  period: string;
  startDate: string;
  endDate: string;
  totalQueries: number;
  totalTokens: number;
  totalInvestigations: number;
}
