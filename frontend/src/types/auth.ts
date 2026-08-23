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

/** Last logged HTTP exchange for an API key (dashboard modal). */
export interface ApiKeyRecentRequest {
  id: number;
  createdAt: string;
  method: string;
  path: string;
  statusCode: number;
  request: string;
  response: string;
  requestTruncated: boolean;
  responseTruncated: boolean;
  streamResponse: boolean;
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

export interface QuerySeriesPoint {
  bucketStart: string;
  count: number;
}

export interface QuerySeries {
  last7Days: QuerySeriesPoint[];
  last30Days: QuerySeriesPoint[];
  last12Weeks: QuerySeriesPoint[];
  last12Months: QuerySeriesPoint[];
}

/** GET /v1/system-stats/health — multi-LLM aware (Ollama, Vast, clinic, third-party APIs). */
export interface HealthSnapshot {
  status: string;
  timestamp: string;
  backend?: { status: string };
  model: { version: string; status: string };
  servers: { primary?: string; secondary?: string; cpu?: string; gpu?: string };
  inference_summary?: {
    ollama_default: string;
    ollama_clinic: string | null;
    clinic_configured: boolean;
    serverless_configured: boolean;
    third_party_models: number;
  };
  lastCheck?: string;
  serverless?: { ollama_endpoint: string | null; api_key_configured: boolean };
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
  totalQueries1h?: number;
  totalQueries24h: number;
  totalQueriesWeek: number;
  totalQueriesMonth: number;
  errorRate24h: number;
  lastHealthCheck?: string;
}

export type DashboardLevel = 'ok' | 'warning' | 'error';

/** GET /v1/api/system-stats/dashboard-overview — admin overview cards. */
export interface DashboardOverview {
  overall: { status?: string; timestamp?: string };
  health_checks: Array<{
    key: string;
    label: string;
    level: DashboardLevel;
    detail?: string | null;
  }>;
  servers: Array<{
    id: string;
    label: string;
    kind: string;
    up: boolean;
    state: string;
    level: DashboardLevel;
    detail?: string | null;
    instance_id?: string | null;
    name_tag?: string | null;
    instance_type?: string | null;
    primary_key?: string | null;
    estimated_monthly_usd?: number | null;
    estimated_daily_usd?: number | null;
  }>;
  queries: { last1h: number; last24h: number; last7d: number; last30d: number };
  sources: Array<{
    key: string;
    label: string;
    level: DashboardLevel;
    count: number | null;
    detail?: string | null;
  }>;
  sources_legacy?: {
    vector_documents: number;
    indexed_sources: number;
    directory_specialists: number;
    allcan_organizations: number | null;
  };
  users: { total: number; admins: number; researchers: number; developers: number };
  ingestion?: {
    jobs: Array<{
      id: string;
      kind: string;
      label: string;
      detail: string;
      source_type?: string;
      source_site?: string;
      /** ISO 8601 — última actividad de ingesta (embed: último índice/actualización; scrape: max last_scraped o inicio de run). */
      last_ingestion_at?: string | null;
      /** Chunks indexados (RAG) o perfiles upserted (scrape). */
      results_count?: number | null;
    }>;
  };
  health: HealthSnapshot;
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
