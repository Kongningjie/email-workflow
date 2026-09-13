import type {
  ApiErrorPayload,
  ImportResult,
  PayloadPreview,
  Plan,
  PlanSummary,
  ReviewRecord,
  Submission,
  TestPlanContent,
  ValidationResult,
} from './types'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly field: string | null,
    readonly requestId: string | null,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (init?.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(`/api/v1${path}`, { ...init, headers })
  if (!response.ok) {
    let payload: ApiErrorPayload = {}
    try {
      payload = (await response.json()) as ApiErrorPayload
    } catch {
      // 非 JSON 错误统一转换为安全前端消息。
    }
    const detail = payload.error
    throw new ApiError(
      detail?.message ?? '请求失败，请稍后重试',
      response.status,
      detail?.code ?? 'request_failed',
      detail?.field ?? null,
      detail?.request_id ?? response.headers.get('X-Request-Id'),
    )
  }
  return (await response.json()) as T
}

export const api = {
  importEmail(file: File, confirmed: boolean) {
    const body = new FormData()
    body.set('file', file)
    body.set('confirm_external_processing', String(confirmed))
    return request<ImportResult>('/imports', { method: 'POST', body })
  },
  listPlans: () => request<PlanSummary[]>('/test-plans'),
  getPlan: (id: string) => request<Plan>(`/test-plans/${id}`),
  savePlan(id: string, baseVersion: number, content: TestPlanContent) {
    return request<{ created: boolean; version: Plan['version'] }>(`/test-plans/${id}/versions`, {
      method: 'POST',
      body: JSON.stringify({ base_version: baseVersion, content }),
    })
  },
  validatePlan: (id: string) =>
    request<ValidationResult>(`/test-plans/${id}/validate`, { method: 'POST' }),
  submitForReview: (id: string) =>
    request<ValidationResult>(`/test-plans/${id}/submit-for-review`, { method: 'POST' }),
  listReviews: (id: string) => request<ReviewRecord[]>(`/test-plans/${id}/reviews`),
  reviewPlan(
    id: string,
    body: {
      decision: 'approved' | 'revision_requested'
      operator_name: string
      operator_employee_id: string
      comment: string | null
      validation_run_id: string | null
      acknowledged_warning_ids: string[]
    },
  ) {
    return request<ReviewRecord>(`/test-plans/${id}/reviews`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },
  getEvidence: (id: string) =>
    request<{ id: string; section_type: string; safe_excerpt: string | null; purged_at: string | null }>(
      `/evidence/${id}`,
    ),
  createPreview: (id: string) =>
    request<PayloadPreview>(`/test-plans/${id}/payload-previews`, { method: 'POST' }),
  listSubmissions: (id: string) => request<Submission[]>(`/test-plans/${id}/submissions`),
  confirmSubmission(
    id: string,
    body: {
      confirmation_token: string
      payload_sha256: string
      operator_name: string
      operator_employee_id: string
    },
  ) {
    return request<Submission>(`/test-plans/${id}/submissions`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },
  reconcileSubmission: (id: string) =>
    request<Submission>(`/submissions/${id}/reconcile`, { method: 'POST' }),
  retrySubmission: (id: string) =>
    request<Submission>(`/submissions/${id}/retry`, { method: 'POST' }),
}
