export type WorkflowStatus =
  | "pending"
  | "processing"
  | "retry_scheduled"
  | "failed"
  | "needs_review"
  | "completed"
  | "compensated";

export type WorkflowStep = "validate_order" | "reserve_inventory" | "generate_invoice";

export type ActionType =
  | "retry_workflow"
  | "reconcile_and_resume"
  | "mark_for_review"
  | "release_reservation";
export type RecommendedAction = ActionType | "no_action";

export type RecoveryStatus =
  | "requested"
  | "approved"
  | "rejected"
  | "queued"
  | "executing"
  | "executed"
  | "failed";

export type InvestigationStatus = "pending" | "running" | "completed" | "failed";

export interface User {
  id: string;
  username: string;
  email: string;
  role: "admin" | "operator";
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface Workflow {
  id: string;
  order_id: string;
  status: WorkflowStatus;
  current_step: WorkflowStep | null;
  attempts: number;
  next_retry_at: string | null;
  /** Only returned by the single-workflow endpoint. */
  reservation_status?: string | null;
  has_invoice?: boolean | null;
  last_error_code: string | null;
  last_error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowSummary extends Workflow {
  product_id: string;
  quantity: number;
  order_status: string;
}

export interface OrderListItem {
  id: string;
  user_id: string;
  product_id: string;
  quantity: number;
  status: string;
  created_at: string;
  updated_at: string;
  workflow_id: string;
  workflow_status: WorkflowStatus;
}

export interface OrderAccepted {
  order_id: string;
  workflow_id: string;
  status: string;
  message: string;
}

export interface WorkflowEvent {
  id: string;
  workflow_id: string;
  step: WorkflowStep | null;
  event_type: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface EvidenceItem {
  source: string;
  reference: string;
  observation: string;
}

export interface Investigation {
  id: string;
  workflow_id: string;
  status: InvestigationStatus;
  root_cause: string | null;
  recommended_action: RecommendedAction | null;
  reasoning: string | null;
  evidence: EvidenceItem[];
  confidence: number | null;
  requires_approval: boolean;
  policy_result: {
    model_recommended_action: string;
    final_action: string;
    downgraded: boolean;
    violations: string[];
    unsupported_references: string[];
  } | null;
  error_message: string | null;
  model_name: string | null;
  prompt_version: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  latency_ms: number | null;
  created_at: string;
  updated_at: string;
  my_feedback?: { rating: FeedbackRating; comment: string | null; updated_at: string } | null;
}

export type FeedbackRating = "helpful" | "not_helpful";

export interface InvestigationMetrics {
  window_days: number;
  investigations: { total: number; completed: number; failed: number; in_flight: number };
  model: {
    avg_confidence: number | null;
    avg_latency_ms: number | null;
    max_latency_ms: number | null;
    prompt_tokens: number;
    completion_tokens: number;
  };
  guardrails: {
    downgraded: number;
    downgrade_rate: number | null;
    unsupported_reference_rate: number | null;
    top_violations: { reason: string; count: number }[];
  };
  actions: { final: Record<string, number>; model_original: Record<string, number> };
  outcomes: {
    actionable: number;
    followed: number;
    approved: number;
    rejected: number;
    executed: number;
    succeeded: number;
    overridden: number;
    no_recovery_requested: number;
    follow_rate: number | null;
    approval_rate: number | null;
    success_rate: number | null;
  };
  calibration: {
    bucket: string;
    actionable: number;
    followed: number;
    executed: number;
    succeeded: number;
    success_rate: number | null;
  }[];
  feedback: {
    helpful: number;
    not_helpful: number;
    helpful_rate: number | null;
    coverage: number | null;
  };
}

export interface RecoveryAction {
  id: string;
  workflow_id: string;
  action_type: ActionType;
  status: RecoveryStatus;
  reason: string;
  investigation_id: string | null;
  requested_by: string;
  approved_by: string | null;
  approved_at: string | null;
  rejected_by: string | null;
  rejected_at: string | null;
  rejection_reason: string | null;
  executed_at: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const TOKEN_KEY = "awr.token";

export const tokenStore = {
  get: (): string | null => {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set: (token: string) => {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* storage unavailable: session lasts until reload */
    }
  },
  clear: () => {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ignore */
    }
  },
};

let unauthorizedHandler: (() => void) | null = null;

export function onUnauthorized(handler: () => void) {
  unauthorizedHandler = handler;
}

function describe(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof d === "object" && d && "msg" in d ? String((d as { msg: unknown }).msg) : String(d)))
      .join("; ");
  }
  return fallback;
}

let memoryToken: string | null = null;

export function setSessionToken(token: string | null) {
  memoryToken = token;
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; form?: Record<string, string>; headers?: Record<string, string> } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
  const token = memoryToken ?? tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;

  let body: BodyInit | undefined;
  if (options.form) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    body = new URLSearchParams(options.form).toString();
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, { method: options.method ?? "GET", headers, body });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is the backend running?");
  }

  if (response.status === 401 && token && !path.startsWith("/auth/login")) {
    unauthorizedHandler?.();
  }

  if (!response.ok) {
    let detail: unknown;
    try {
      detail = (await response.json()).detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, describe(detail, `Request failed (${response.status})`));
  }

  return (await response.json()) as T;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string }>("/auth/login", { method: "POST", form: { username, password } }),
  register: (username: string, email: string, password: string) =>
    request<User>("/auth/register", { method: "POST", body: { username, email, password } }),
  me: () => request<User>("/auth/me"),

  orders: () => request<OrderListItem[]>("/orders?limit=100"),
  createOrder: (product_id: string, quantity: number, idempotencyKey: string) =>
    request<OrderAccepted>("/orders", {
      method: "POST",
      body: { product_id, quantity },
      headers: { "Idempotency-Key": idempotencyKey },
    }),

  workflows: (status?: WorkflowStatus) =>
    request<WorkflowSummary[]>(`/workflows?limit=200${status ? `&status=${status}` : ""}`),
  workflow: (id: string) => request<Workflow>(`/workflows/${id}`),
  heldStock: () => request<WorkflowSummary[]>("/workflows/held-stock?limit=200"),
  events: (id: string) => request<WorkflowEvent[]>(`/workflows/${id}/events`),

  investigations: (workflowId: string) =>
    request<Investigation[]>(`/workflows/${workflowId}/investigations`),
  investigationMetrics: (days: number) =>
    request<InvestigationMetrics>(`/investigation-metrics?days=${days}`),
  giveFeedback: (investigationId: string, rating: FeedbackRating, comment: string | null) =>
    request<{ rating: FeedbackRating; comment: string | null; updated_at: string }>(
      `/investigations/${investigationId}/feedback`,
      { method: "PUT", body: { rating, comment } },
    ),
  investigate: (workflowId: string) =>
    request<Investigation>(`/workflows/${workflowId}/investigate`, { method: "POST" }),

  recoveryActions: (workflowId: string) =>
    request<RecoveryAction[]>(`/workflows/${workflowId}/recovery-actions`),
  recoveryQueue: (status?: RecoveryStatus) =>
    request<RecoveryAction[]>(`/recovery-actions?limit=200${status ? `&status=${status}` : ""}`),
  requestRecovery: (
    workflowId: string,
    body: { action_type: ActionType; reason: string; investigation_id?: string | null },
    idempotencyKey: string,
  ) =>
    request<RecoveryAction>(`/workflows/${workflowId}/recovery-actions`, {
      method: "POST",
      body,
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  approve: (workflowId: string, actionId: string) =>
    request<RecoveryAction>(`/workflows/${workflowId}/recovery-actions/${actionId}/approve`, {
      method: "POST",
    }),
  reject: (workflowId: string, actionId: string, reason: string) =>
    request<RecoveryAction>(`/workflows/${workflowId}/recovery-actions/${actionId}/reject`, {
      method: "POST",
      body: { reason },
    }),
  execute: (workflowId: string, actionId: string) =>
    request<RecoveryAction>(`/workflows/${workflowId}/recovery-actions/${actionId}/execute`, {
      method: "POST",
    }),
};

export async function fetchText(path: string): Promise<{ ok: boolean; text: string }> {
  const response = await fetch(path);
  return { ok: response.ok, text: await response.text() };
}
