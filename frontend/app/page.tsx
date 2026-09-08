"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  api,
  AgentJob,
  ApiError,
  Conversation,
  DashboardProduct,
  Escalation,
  Message,
  SecurityAuditEvent,
  User,
} from "../lib/api";
import { MessageContent } from "../components/MessageContent";
import { Dashboard } from "../components/Dashboard";
import { HomeDashboard } from "../components/HomeDashboard";
import { TrashIcon } from "../components/Icons";

const statusLabel: Record<string, string> = {
  no_evidence: "근거 부족",
  conflict: "정책 충돌",
  escalation: "담당자 확인 필요",
};

const loadingStages = [
  "질문을 확인하고 있습니다…",
  "필요한 데이터와 정책을 확인하고 있습니다…",
  "답변에 사용할 근거를 확인하고 있습니다…",
  "확인된 내용을 정리하고 있습니다…",
];

function conversationTitle(content: string) {
  const normalized = content.replace(/\s+/g, " ").trim();
  return normalized.length > 32 ? `${normalized.slice(0, 31).trim()}…` : normalized;
}

async function waitForAgentJob(jobId: string) {
  const deadline = Date.now() + 150_000;
  while (Date.now() < deadline) {
    const job = await api<AgentJob>(`/api/conversation-jobs/${jobId}`);
    if (job.status === "succeeded") return job;
    if (job.status === "failed") {
      throw new ApiError(
        job.error || "답변을 생성하지 못했습니다.",
        job.http_status || 500,
      );
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
  }
  throw new ApiError(
    "답변 생성이 계속 진행 중입니다. 잠시 후 대화를 다시 열어 확인해 주세요.",
    504,
  );
}

export default function Home() {
  const [authConfig, setAuthConfig] = useState({ oidc_enabled: false, dev_login_enabled: false, oidc_provider: "google" });
  const [user, setUser] = useState<User | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [active, setActive] = useState<Conversation | null>(null);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingStage, setLoadingStage] = useState(0);
  const [error, setError] = useState("");
  const [devEmail, setDevEmail] = useState("employee@example.com");
  const [view, setView] = useState<"home" | "chat" | "dashboard" | "escalations" | "admin">("home");
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [adminUsers, setAdminUsers] = useState<User[]>([]);
  const [auditEvents, setAuditEvents] = useState<SecurityAuditEvent[]>([]);

  const errorMessage = useCallback((reason: unknown, fallback: string) => {
    if (reason instanceof ApiError && reason.requestId) {
      return `${reason.message} (요청 ID: ${reason.requestId})`;
    }
    return reason instanceof Error ? reason.message : fallback;
  }, []);

  async function loadConversations() {
    const rows = await api<Conversation[]>("/api/conversations");
    setConversations(rows);
    if (rows.length && !active) await openConversation(rows[0].conversation_id);
  }

  async function openConversation(id: string) {
    setError("");
    try {
      setActive(await api<Conversation>(`/api/conversations/${id}`));
    } catch (reason) {
      setError(errorMessage(reason, "대화를 불러오지 못했습니다."));
    }
  }

  async function openOperations(nextView: "escalations" | "admin") {
    setError("");
    setLoading(true);
    try {
      if (nextView === "escalations") {
        setEscalations(await api<Escalation[]>("/api/escalations"));
      } else {
        const [users, events] = await Promise.all([
          api<User[]>("/api/admin/users"),
          api<SecurityAuditEvent[]>("/api/admin/security-audit-events?limit=50"),
        ]);
        setAdminUsers(users);
        setAuditEvents(events);
      }
      setView(nextView);
    } catch (reason) {
      setError(errorMessage(reason, "운영 정보를 불러오지 못했습니다."));
    } finally {
      setLoading(false);
    }
  }

  async function updateEscalation(
    escalationId: string,
    status: Escalation["status"],
  ) {
    setError("");
    try {
      await api(`/api/escalations/${escalationId}`, {
        method: "PUT",
        body: JSON.stringify({ status }),
      });
      setEscalations(await api<Escalation[]>("/api/escalations"));
    } catch (reason) {
      setError(errorMessage(reason, "Escalation 상태 변경에 실패했습니다."));
    }
  }

  useEffect(() => {
    api<{ oidc_enabled: boolean; dev_login_enabled: boolean; oidc_provider: string }>("/api/auth/config").then(setAuthConfig).catch(() => undefined);
    api<User>("/api/auth/me")
      .then((value) => {
        setUser(value);
        return api<Conversation[]>("/api/conversations");
      })
      .then(setConversations)
      .catch((reason) => {
        setUser(null);
        if (!(reason instanceof ApiError && reason.status === 401)) {
          setError(errorMessage(reason, "서비스 상태를 확인할 수 없습니다."));
        }
      });
  }, []);

  useEffect(() => {
    if (!loading) {
      setLoadingStage(0);
      return;
    }
    const timer = window.setInterval(() => {
      setLoadingStage((current) => Math.min(current + 1, loadingStages.length - 1));
    }, 2500);
    return () => window.clearInterval(timer);
  }, [loading]);

  async function devLogin(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const loggedIn = await api<User>("/api/auth/dev-login", {
        method: "POST",
        body: JSON.stringify({ email: devEmail, display_name: "개발 사용자" }),
      });
      setUser(loggedIn);
      await loadConversations();
    } catch (reason) {
      setError(errorMessage(reason, "로그인 실패"));
    }
  }

  async function createPolicyConversation(initialQuestion = "") {
    setError("");
    try {
      const created = await api<Conversation>("/api/conversations", {
        method: "POST",
        body: JSON.stringify({ title: "새 대화", context_mode: "general" }),
      });
      setConversations((items) => [created, ...items]);
      setActive({ ...created, messages: [] });
      setView("chat");
      setQuestion(initialQuestion);
    } catch (reason) {
      setError(errorMessage(reason, "새 대화를 만들지 못했습니다."));
    }
  }

  async function startPolicyConversation(initialQuestion: string) {
    await createPolicyConversation(initialQuestion);
  }

  async function startFreshPolicyConversation() {
    if (question.trim() && !window.confirm("작성 중인 질문을 지우고 새 정책 대화를 시작할까요?")) return;
    await startPolicyConversation("");
  }

  async function startProductConversation(product: DashboardProduct) {
    setError("");
    try {
      const created = await api<Conversation>("/api/conversations", {
        method: "POST",
        body: JSON.stringify({
          title: "새 대화",
          context_mode: "product",
          product_parent_asin: product.parent_asin,
        }),
      });
      setConversations((items) => [created, ...items]);
      setActive({ ...created, messages: [] });
      setView("chat");
      setQuestion("");
    } catch (reason) {
      setError(errorMessage(reason, "상품 대화를 만들지 못했습니다."));
    }
  }

  async function logout() {
    setError("");
    try {
      await api<void>("/api/auth/logout", { method: "POST" });
      setUser(null);
      setConversations([]);
      setActive(null);
      setQuestion("");
      setView("home");
    } catch (reason) {
      setError(errorMessage(reason, "로그아웃 실패"));
    }
  }

  async function archiveConversation(conversationId: string) {
    const conversation = conversations.find(
      (item) => item.conversation_id === conversationId,
    );
    if (!conversation) return;
    if (!window.confirm(`“${conversation.title}” 대화를 목록에서 삭제할까요?\n감사·근거 이력은 보존됩니다.`)) return;

    setError("");
    try {
      await api<void>(`/api/conversations/${conversationId}`, { method: "DELETE" });
      setConversations((items) => items.filter(
        (item) => item.conversation_id !== conversationId,
      ));
      if (active?.conversation_id === conversationId) {
        setActive(null);
        setQuestion("");
        setView("home");
      }
    } catch (reason) {
      setError(errorMessage(reason, "대화를 삭제하지 못했습니다."));
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || !active || loading) return;
    const content = question.trim();
    const conversationId = active.conversation_id;
    const pendingId = `pending-${Date.now()}`;
    const pendingMessage: Message = {
      message_id: pendingId,
      role: "user",
      content,
      created_at: new Date().toISOString(),
      sources: [],
      delivery_state: "sending",
    };
    const nextTitle = active.title === "새 대화" ? conversationTitle(content) : active.title;
    setQuestion("");
    setActive((current) => current ? {
      ...current,
      title: nextTitle,
      messages: [...(current.messages ?? []), pendingMessage],
    } : current);
    setConversations((items) => items.map((item) =>
      item.conversation_id === conversationId ? { ...item, title: nextTitle } : item
    ));
    setLoading(true);
    setError("");
    try {
      const job = await api<AgentJob>(`/api/conversations/${conversationId}/messages`, {
        method: "POST",
        body: JSON.stringify({ content }),
      });
      await waitForAgentJob(job.job_id);
      await openConversation(conversationId);
      await loadConversations();
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) {
        setUser(null);
        setActive(null);
        setConversations([]);
      } else {
        try {
          const current = await api<Conversation>(`/api/conversations/${conversationId}`);
          const wasSaved = (current.messages ?? []).some(
            (message) => message.role === "user" && message.content === content,
          );
          if (wasSaved) {
            setActive(current);
          } else {
            setQuestion(content);
            setActive((value) => value ? {
              ...value,
              messages: (value.messages ?? []).map((message) =>
                message.message_id === pendingId
                  ? { ...message, delivery_state: "failed" }
                  : message
              ),
            } : value);
          }
        } catch {
          setQuestion(content);
          setActive((value) => value ? {
            ...value,
            messages: (value.messages ?? []).map((message) =>
              message.message_id === pendingId
                ? { ...message, delivery_state: "failed" }
                : message
            ),
          } : value);
        }
      }
      setError(errorMessage(reason, "답변 생성 실패"));
    } finally {
      setLoading(false);
    }
  }

  if (!user) {
    return (
      <main className="login-shell">
        <section className="login-card">
          <p className="eyebrow">CUSTOMER INTELLIGENCE</p>
          <h1>정책과 고객 데이터를<br />하나의 대화로 확인하세요.</h1>
          <p className="muted">회사 계정으로 로그인하거나 개발 환경 로그인을 사용합니다.</p>
          {authConfig.oidc_enabled && <a className="primary button" href="/api/auth/login">{authConfig.oidc_provider === "google" ? "Google로 로그인" : "회사 계정으로 로그인"}</a>}
          {authConfig.dev_login_enabled && <form onSubmit={devLogin} className="dev-login">
            <input value={devEmail} onChange={(event) => setDevEmail(event.target.value)} type="email" />
            <button type="submit">개발 로그인</button>
          </form>}
          {!authConfig.oidc_enabled && !authConfig.dev_login_enabled && <p className="error">로그인 방식이 아직 설정되지 않았습니다.</p>}
          {error && <p className="error">{error}</p>}
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <aside>
        <div className="account">
          <p className="eyebrow">CUSTOMER INTELLIGENCE</p>
          <strong>{user.display_name}</strong>
          <p className="muted small">{user.role} · {user.email}</p>
          {user.policy_scopes.length === 0 && (
            <p className="scope-warning">정책 검색 권한이 없습니다.</p>
          )}
          <button className="logout" onClick={logout}>로그아웃</button>
        </div>
        <div className="role-navigation">
          <button className={view === "home" ? "active" : ""} onClick={() => { setError(""); setView("home"); }}>홈</button>
          <button className={view === "dashboard" ? "active" : ""} onClick={() => { setError(""); setView("dashboard"); }}>상품 분석</button>
          {(user.role === "manager" || user.role === "admin") && (
            <button className={view === "escalations" ? "active" : ""} onClick={() => openOperations("escalations")}>Escalation</button>
          )}
          {user.role === "admin" && (
            <button className={view === "admin" ? "active" : ""} onClick={() => openOperations("admin")}>사용자·감사</button>
          )}
        </div>
        <nav>
          {conversations.map((conversation) => (
            <div className={`conversation-item ${view === "chat" && active?.conversation_id === conversation.conversation_id ? "active" : ""}`} key={conversation.conversation_id}>
              <button className="conversation-open" onClick={() => { setView("chat"); openConversation(conversation.conversation_id); }}>
                <strong>{conversation.title}</strong>
                {conversation.context_mode === "product" && <span className="conversation-product">{conversation.product_store || "상품"} · {conversation.product_parent_asin}</span>}
              </button>
              <button className="conversation-delete" disabled={loading && active?.conversation_id === conversation.conversation_id} aria-label={`${conversation.title} 대화 삭제`} title="대화 삭제" onClick={() => archiveConversation(conversation.conversation_id)}><TrashIcon /></button>
            </div>
          ))}
        </nav>
      </aside>
      {view === "home" && <HomeDashboard user={user} conversations={conversations} onOpenConversation={(id) => { setView("chat"); openConversation(id); }} onOpenProducts={() => { setError(""); setView("dashboard"); }} onStartPolicyConversation={startPolicyConversation} />}
      {view === "home" && error && <p className="error floating-banner" role="alert">{error}</p>}
      {view === "chat" && <section className="chat-panel">
        <header className="chat-header">
          <div>
            <h2>{active?.title ?? "대화를 선택하세요"}</h2>
            {active?.context_mode === "product" && <p className="chat-product-context"><span>현재 상품</span><strong>{active.product_title}</strong><small>{active.product_store || "스토어 미상"} · {active.product_parent_asin}</small></p>}
          </div>
          {active?.context_mode === "product" && <button className="secondary-button" onClick={() => setView("dashboard")}>다른 상품 선택</button>}
          {active?.context_mode === "general" && <button className="secondary-button" disabled={loading || user.policy_scopes.length === 0} onClick={startFreshPolicyConversation}>새 정책 질문</button>}
        </header>
        <div className="messages">
          {(active?.messages ?? []).map((message: Message) => (
            <article key={message.message_id} className={`message ${message.role}`}>
              {message.response_status && message.response_status !== "answer" && <span className={`status ${message.response_status}`}>{statusLabel[message.response_status]}</span>}
              <MessageContent content={message.content} />
              {message.delivery_state === "sending" && <span className="delivery-state">전송 중</span>}
              {message.delivery_state === "failed" && <span className="delivery-state failed">전송을 확인하지 못했습니다</span>}
              {!!message.sources?.length && <details><summary>정책 근거 {message.sources.length}개</summary>{message.sources.map((source) => <div className="source" key={source.source_id}><div className="source-heading"><strong>{source.title}</strong><span className="source-scope">{source.metadata ? (source.metadata.product_specific ? "상품 전용" : "전 상품 공통") : "범위 정보 없음"}</span></div><span>{source.version_number ? `v${source.version_number}` : "버전 미상"} · {source.section_title || "섹션 미상"}</span>{(source.metadata?.jurisdiction || source.metadata?.department || source.metadata?.collection) && <small>{[source.metadata?.jurisdiction, source.metadata?.department, source.metadata?.collection].filter(Boolean).join(" · ")}</small>}</div>)}</details>}
            </article>
          ))}
          {loading && <article className="message assistant pending-response" aria-live="polite"><span className="spinner" aria-hidden="true" /><p>{loadingStages[loadingStage]}</p></article>}
        </div>
        {active?.context_mode === "product" && <div className="suggested-questions"><span>추천 질문</span><button onClick={() => setQuestion("이 상품의 반복 불만과 개선 우선순위를 알려줘.")}>반복 불만 분석</button><button onClick={() => setQuestion("이 상품의 평점 분포와 주요 고객 반응을 알려줘.")}>평점·고객 반응</button><button onClick={() => setQuestion("이 상품에 적용되는 환불·재배송 정책을 알려줘.")}>관련 정책 확인</button></div>}
        {active ? <form className="composer" onSubmit={submit}><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={active.context_mode === "product" ? "선택한 상품의 리뷰, 개선점 또는 적용 정책을 질문하세요." : "승인된 업무 정책에 대해 질문하세요."} /><button className="primary" disabled={loading}>전송</button></form> : <div className="empty"><div><strong>홈에서 업무를 선택해 주세요.</strong><button className="secondary-button" onClick={() => setView("home")}>홈으로 이동</button></div></div>}
        {error && <p className="error banner" role="alert">{error}</p>}
      </section>}
      {view === "dashboard" && <Dashboard onError={setError} errorMessage={errorMessage} onStartProductConversation={startProductConversation} />}
      {view === "dashboard" && error && <p className="error floating-banner" role="alert">{error}</p>}
      {view === "escalations" && <section className="operations-panel">
        <header>
          <div><p className="eyebrow">HUMAN REVIEW</p><h2>Escalation 관리</h2></div>
          <button onClick={() => openOperations("escalations")}>새로고침</button>
        </header>
        <div className="operations-list">
          {escalations.length === 0 && <p className="muted">확인이 필요한 건이 없습니다.</p>}
          {escalations.map((item) => <article className="operation-card" key={item.escalation_id}>
            <div className="operation-heading"><strong>{item.category}</strong><span className={`status ${item.status}`}>{item.status}</span></div>
            <p>{item.reason}</p>
            <p className="muted small">발생 {item.occurrence_count}회 · {new Date(item.last_occurred_at).toLocaleString("ko-KR")}</p>
            <div className="actions">
              <button disabled={item.status === "acknowledged"} onClick={() => updateEscalation(item.escalation_id, "acknowledged")}>확인 중</button>
              <button disabled={item.status === "resolved"} onClick={() => updateEscalation(item.escalation_id, "resolved")}>처리 완료</button>
            </div>
          </article>)}
        </div>
        {error && <p className="error banner" role="alert">{error}</p>}
      </section>}
      {view === "admin" && <section className="operations-panel">
        <header>
          <div><p className="eyebrow">ADMIN</p><h2>사용자와 보안 감사</h2></div>
          <button onClick={() => openOperations("admin")}>새로고침</button>
        </header>
        <div className="admin-grid">
          <section>
            <h3>사용자</h3>
            <div className="operations-list compact">
              {adminUsers.map((item) => <article className="operation-card" key={item.user_id}>
                <div className="operation-heading"><strong>{item.display_name}</strong><span className="role-badge">{item.role}</span></div>
                <p className="muted small">{item.email}</p>
                <p className="small">정책 범위 {item.policy_scopes.length}개 · {item.is_active ? "활성" : "비활성"}</p>
              </article>)}
            </div>
          </section>
          <section>
            <h3>최근 감사 이벤트</h3>
            <div className="audit-list">
              {auditEvents.map((item) => <article key={item.audit_event_id}>
                <strong>{item.event_type}</strong><span className={`audit-outcome ${item.outcome}`}>{item.outcome}</span>
                <p className="muted small">{new Date(item.occurred_at).toLocaleString("ko-KR")} · 요청 {item.request_id}</p>
              </article>)}
            </div>
          </section>
        </div>
        {error && <p className="error banner" role="alert">{error}</p>}
      </section>}
    </main>
  );
}
