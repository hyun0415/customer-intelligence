export type User = {
  user_id: number;
  email: string;
  display_name: string;
  role: "employee" | "manager" | "admin";
  is_active: boolean;
  policy_scopes: PolicyScope[];
};

export type PolicyScope = {
  collection: string;
  jurisdiction: string;
  department: string;
};

export type Source = {
  source_id: string;
  title: string;
  version_number?: number;
  section_title?: string;
  metadata?: {
    collection?: string;
    authority_tier?: number;
    jurisdiction?: string;
    department?: string;
    parent_asins?: string[];
    product_specific?: boolean;
  };
};

export type Message = {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  response_status?: "answer" | "no_evidence" | "conflict" | "escalation";
  created_at: string;
  sources: Source[];
  delivery_state?: "sending" | "failed";
};

export type Conversation = {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages?: Message[];
  context_mode: "general" | "product";
  product_parent_asin: string | null;
  product_title: string | null;
  product_store: string | null;
};

export type Escalation = {
  escalation_id: string;
  conversation_id: string;
  email: string;
  category: string;
  reason: string;
  status: "open" | "acknowledged" | "resolved";
  occurrence_count: number;
  last_occurred_at: string;
};

export type SecurityAuditEvent = {
  audit_event_id: string;
  occurred_at: string;
  event_type: string;
  outcome: string;
  actor_user_id?: number;
  request_id: string;
  resource_type?: string;
  resource_id?: string;
};

export type DashboardProduct = {
  parent_asin: string;
  title: string;
  store: string | null;
  average_rating: number | null;
  review_count: number;
  negative_count: number;
  negative_ratio: number;
  verified_count: number;
  verified_ratio: number;
};

export type DashboardReview = {
  review_id: number;
  rating: number;
  review_title: string | null;
  review_text: string | null;
  reviewed_at: string;
  helpful_vote: number;
  verified_purchase: boolean;
};

export type DashboardProductDetail = DashboardProduct & {
  rating_distribution: { rating: number; review_count: number }[];
  representative_reviews: DashboardReview[];
  min_review_at: string | null;
  max_review_at: string | null;
};

export type ReviewPatternResult = {
  sample_size: number;
  ratio_denominator: number;
  extracted_review_count: number;
  pattern_review_count: number;
  patterns: {
    topic: string;
    label: string;
    description: string;
    count: number;
    ratio: number;
    average_confidence: number;
    evidence: {
      source_index: number;
      evidence: string;
      confidence: number;
      review_summary: string;
    }[];
  }[];
};

export type AspectJob = {
  job_id: string;
  parent_asin: string;
  status: "queued" | "running" | "succeeded" | "failed";
  result?: ReviewPatternResult;
  error?: string;
};

export type AgentJob = {
  job_id: string;
  conversation_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  result?: {
    status: string;
    message: Message;
    sources: Source[];
  };
  http_status?: number;
  error?: string;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get retryable() {
    return this.status === 0 || this.status === 429 || this.status >= 500;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  // Agent POST를 자동 재시도하면 질문이 중복 저장될 수 있으므로, timeout 시
  // 입력을 복원하고 사용자가 명시적으로 재시도하도록 한다.
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 130_000);
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      credentials: "include",
      signal: init?.signal ?? controller.signal,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === "AbortError") {
      throw new ApiError(
        "응답 대기 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.",
        0,
      );
    }
    throw new ApiError(
      "서버에 연결할 수 없습니다. 네트워크 상태를 확인한 뒤 다시 시도해 주세요.",
      0,
    );
  } finally {
    window.clearTimeout(timeout);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail && typeof detail.message === "string"
          ? detail.message
        : Array.isArray(detail)
          ? detail.map((item) => item?.msg ?? JSON.stringify(item)).join(", ")
          : `요청 실패 (${response.status})`;
    throw new ApiError(
      message,
      response.status,
      response.headers.get("X-Request-ID") ?? payload?.request_id,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
