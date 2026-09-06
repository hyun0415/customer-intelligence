export type User = {
  user_id: number;
  email: string;
  display_name: string;
  role: "employee" | "manager" | "admin";
};

export type Source = {
  source_id: string;
  title: string;
  version_number?: number;
  section_title?: string;
};

export type Message = {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  response_status?: "answer" | "no_evidence" | "conflict" | "escalation";
  created_at: string;
  sources: Source[];
};

export type Conversation = {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages?: Message[];
};

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((item) => item?.msg ?? JSON.stringify(item)).join(", ")
          : `요청 실패 (${response.status})`;
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
