/**
 * Feedback service for message thumbs up/down.
 * Works for both authenticated and anonymous users.
 */

import { getToken } from './auth';

export const REASON_CATEGORIES = [
  { value: 'incorrecta_o_incompleta', label: 'Incorrecta o incompleta' },
  { value: 'no_es_lo_que_pedi', label: 'No es lo que pedí' },
  { value: 'lento_o_con_errores', label: 'Lento o con errores' },
  { value: 'estilo_o_tono', label: 'Estilo o tono' },
  { value: 'problema_seguridad_legal', label: 'Problema de seguridad o legal' },
  { value: 'otra', label: 'Otra opción' },
] as const;

export interface FeedbackSource {
  title?: string;
  url?: string;
  type?: 'rag' | 'web' | 'pubmed';
  score?: number;
  authors?: string;
  year?: string;
  journal?: string;
  ref_num?: number;
}

export interface FeedbackCreate {
  message_id?: number;
  conversation_id?: number;
  rating: 'positive' | 'negative';
  reason_category?: string;
  reason_text?: string;
  content_preview?: string;
  model_name?: string;
  query_title?: string;
  sources?: FeedbackSource[];
}

export interface FeedbackOut {
  id: number;
  message_id?: number;
  conversation_id?: number;
  user_id?: number;
  user_email?: string;
  rating: string;
  reason_category?: string;
  reason_text?: string;
  content_preview?: string;
  model_name?: string;
  query_title?: string;
  sources?: FeedbackSource[];
  created_at: string;
}

export interface FeedbackListResponse {
  data: FeedbackOut[];
  total: number;
}

export async function submitFeedback(body: FeedbackCreate): Promise<FeedbackOut> {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch('/api/feedback', {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(err.detail || err.message || 'Failed to submit feedback');
  }

  return res.json();
}

export async function listFeedback(
  page: number = 1,
  pageSize: number = 50,
  rating?: 'positive' | 'negative',
): Promise<FeedbackListResponse> {
  const token = getToken();
  if (!token) throw new Error('Authentication required');

  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (rating) params.set('rating', rating);

  const res = await fetch(`/api/feedback?${params}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(err.detail || err.message || 'Failed to load feedback');
  }

  return res.json();
}
