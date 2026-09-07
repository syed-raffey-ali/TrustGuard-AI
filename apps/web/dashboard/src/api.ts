import { GATEWAY_URL } from './config';
import type {
  AnalyzeResponse,
  HealthInfo,
  ModelComparisonResponse,
  ProviderTestResult,
  ProviderUpsert,
  ProvidersResponse,
  SessionDetail,
  SessionReport,
  Stats,
} from './types';

export class ApiError extends Error {
  readonly kind: 'network' | 'http';
  readonly status: number | null;

  constructor(message: string, kind: 'network' | 'http', status: number | null = null) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
  }
}

const TIMEOUT_MS = 15000;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    let res: Response;
    try {
      res = await fetch(`${GATEWAY_URL}${path}`, {
        ...init,
        signal: controller.signal,
        headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
      });
    } catch {
      throw new ApiError(`Cannot reach gateway at ${GATEWAY_URL}`, 'network');
    }
    const text = await res.text();
    if (!res.ok) {
      const snippet = text.trim() ? ` — ${text.trim().slice(0, 240)}` : '';
      throw new ApiError(`HTTP ${res.status} ${res.statusText}${snippet}`, 'http', res.status);
    }
    if (!text) return {} as T;
    try {
      return JSON.parse(text) as T;
    } catch {
      throw new ApiError('Gateway returned invalid JSON', 'http', res.status);
    }
  } finally {
    window.clearTimeout(timer);
  }
}

function enc(segment: string): string {
  return encodeURIComponent(segment);
}

export const api = {
  health: () => request<HealthInfo>('/health'),

  stats: () => request<Stats>('/api/v1/stats'),

  listProviders: () => request<ProvidersResponse>('/api/v1/admin/providers'),

  upsertProvider: (provider: ProviderUpsert) =>
    request<Record<string, unknown>>('/api/v1/admin/providers', {
      method: 'POST',
      body: JSON.stringify(provider),
    }),

  patchProvider: (name: string, patch: Partial<ProviderUpsert>) =>
    request<Record<string, unknown>>(`/api/v1/admin/providers/${enc(name)}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),

  deleteProvider: (name: string) =>
    request<Record<string, unknown>>(`/api/v1/admin/providers/${enc(name)}`, {
      method: 'DELETE',
    }),

  testProvider: (name: string) =>
    request<ProviderTestResult>(`/api/v1/admin/providers/${enc(name)}/test`, { method: 'POST' }),

  startSession: (type: 'call' | 'chat') =>
    request<{ session_id: string }>('/api/v1/sessions/start', {
      method: 'POST',
      body: JSON.stringify({ type }),
    }),

  getSession: (id: string) => request<SessionDetail>(`/api/v1/sessions/${enc(id)}`),

  getReport: (id: string) => request<SessionReport>(`/api/v1/sessions/${enc(id)}/report`),

  getModelComparison: (id: string) =>
    request<ModelComparisonResponse>(`/api/v1/sessions/${enc(id)}/model-comparison`),

  analyzePaste: (body: { text: string; format: 'plain' | 'whatsapp_export'; unknown_caller?: boolean }) =>
    request<AnalyzeResponse>('/api/v1/analyze/paste', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
};
