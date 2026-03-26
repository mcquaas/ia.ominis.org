/**
 * Chat History Service for Ominis Health
 * Handles conversation CRUD operations for authenticated users.
 *
 * All calls go through Next.js API routes (/api/conversations/...)
 * which proxy to the backend. This avoids CORS issues since all
 * requests are same-origin from the browser's perspective.
 */

import { getToken } from './auth';

// ---------- Types ----------

export interface ChatMessageData {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  sources?: Array<{
    title: string;
    url: string;
    score?: number;
    type?: 'rag' | 'web' | 'pubmed';
    ref_num?: number;
  }> | null;
  sources_not_used?: Array<Record<string, unknown>> | null;
  charts?: Array<{
    id: string;
    type: 'bar' | 'line' | 'pie' | string;
    title?: string;
    image: string;
  }> | null;
  has_images: boolean;
  created_at: string;
}

export interface ConversationSummary {
  id: number;
  uuid: string;
  title: string;
  is_saved: boolean;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ChatMessageData[];
}

export interface ConversationListResponse {
  data: ConversationSummary[];
  total: number;
}

// ---------- Helpers ----------

async function fetchChat<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  if (!token) throw new Error('Authentication required');

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
    ...(options.headers || {}),
  };

  // Route through Next.js API routes (same-origin, no CORS)
  const response = await fetch(`/api/conversations${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    if (response.status === 204) return undefined as T;
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || error.message || 'Request failed');
  }

  if (response.status === 204) return undefined as T;
  return response.json();
}

// ---------- API ----------

/**
 * List conversations for the current user (newest first)
 */
export async function listConversations(
  page: number = 1,
  pageSize: number = 50,
): Promise<ConversationListResponse> {
  return fetchChat(`?page=${page}&page_size=${pageSize}`);
}

/**
 * Create a new conversation
 */
export async function createConversation(title?: string): Promise<ConversationDetail> {
  return fetchChat('', {
    method: 'POST',
    body: JSON.stringify({ title: title || null }),
  });
}

/**
 * Get a conversation with all its messages (by id)
 */
export async function getConversation(id: number): Promise<ConversationDetail> {
  return fetchChat(`/${id}`);
}

/**
 * Get a conversation by UUID (for shareable URLs)
 */
export async function getConversationByUuid(uuid: string): Promise<ConversationDetail> {
  return fetchChat(`/uuid/${uuid}`);
}

/**
 * Update a conversation (rename or toggle saved status)
 */
export async function updateConversation(
  id: number,
  data: { title?: string; is_saved?: boolean },
): Promise<ConversationSummary> {
  return fetchChat(`/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

/**
 * Regenerate conversation title using LLM
 */
export async function regenerateTitle(id: number): Promise<ConversationSummary> {
  return fetchChat(`/${id}/regenerate-title`, { method: 'POST' });
}

/**
 * Delete a conversation
 */
export async function deleteConversation(id: number): Promise<void> {
  await fetchChat(`/${id}`, { method: 'DELETE' });
}

/**
 * Delete all conversations for the current user
 */
export async function purgeConversations(): Promise<{ deleted: number }> {
  return fetchChat('/purge', { method: 'DELETE' });
}

/**
 * Add messages to a conversation
 */
export async function addMessages(
  conversationId: number,
  messages: Array<{
    role: 'user' | 'assistant';
    content: string;
    sources?: Array<Record<string, unknown>> | null;
    sources_not_used?: Array<Record<string, unknown>> | null;
    charts?: Array<Record<string, unknown>> | null;
    has_images?: boolean;
  }>,
): Promise<ChatMessageData[]> {
  return fetchChat(`/${conversationId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ messages }),
  });
}
