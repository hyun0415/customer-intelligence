"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  api,
  ApiError,
  Conversation,
  Escalation,
  Message,
  SecurityAuditEvent,
  User,
} from "../lib/api";
import { MessageContent } from "../components/MessageContent";

const statusLabel: Record<string, string> = {
  no_evidence: "근거 부족",
  conflict: "정책 충돌",
  escalation: "담당자 확인 필요",
};

export default function Home() {
  const [authConfig, setAuthConfig] = useState({ oidc_enabled: false, dev_login_enabled: false, oidc_provider: "google" });
  const [user, setUser] = useState<User | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [active, setActive] = useState<Conversation | null>(null);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [devEmail, setDevEmail] = useState("employee@example.com");
  const [view, setView] = useState<"chat" | "escalations" | "admin">("chat");
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [adminUsers, setAdminUsers] = useState<User[]>([]);
  const [auditEvents, setAuditEvents] = useState<SecurityAuditEvent[]>([]);

  function errorMessage(reason: unknown, fallback: string) {
    if (reason instanceof ApiError && reason.requestId) {
      return `${reason.message} (요청 ID: ${reason.requestId})`;
    }
    return reason instanceof Error ? reason.message : fallback;
  }

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

  async function newConversation() {
    setError("");
    try {
      const created = await api<Conversation>("/api/conversations", {
        method: "POST",
        body: JSON.stringify({ title: "새 대화" }),
      });
      setConversations((items) => [created, ...items]);
      setActive({ ...created, messages: [] });
      setView("chat");
    } catch (reason) {
      setError(errorMessage(reason, "새 대화를 만들지 못했습니다."));
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
      setView("chat");
    } catch (reason) {
      setError(errorMessage(reason, "로그아웃 실패"));
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || !active || loading) return;
    const content = question.trim();
    setQuestion("");
    setLoading(true);
    setError("");
    try {
      await api(`/api/conversations/${active.conversation_id}/messages`, {
        method: "POST",
        body: JSON.stringify({ content }),
      });
      await openConversation(active.conversation_id);
      await loadConversations();
    } catch (reason) {
      setQuestion(content);
      if (reason instanceof ApiError && reason.status === 401) {
        setUser(null);
        setActive(null);
        setConversations([]);
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
        <button className="primary" onClick={newConversation}>+ 새 대화</button>
        <div className="role-navigation">
          <button className={view === "chat" ? "active" : ""} onClick={() => setView("chat")}>대화</button>
          {(user.role === "manager" || user.role === "admin") && (
            <button className={view === "escalations" ? "active" : ""} onClick={() => openOperations("escalations")}>Escalation</button>
          )}
          {user.role === "admin" && (
            <button className={view === "admin" ? "active" : ""} onClick={() => openOperations("admin")}>사용자·감사</button>
          )}
        </div>
        <nav>
          {conversations.map((conversation) => (
            <button className={view === "chat" && active?.conversation_id === conversation.conversation_id ? "active" : ""} key={conversation.conversation_id} onClick={() => { setView("chat"); openConversation(conversation.conversation_id); }}>
              {conversation.title}
            </button>
          ))}
        </nav>
      </aside>
      {view === "chat" && <section className="chat-panel">
        <header><h2>{active?.title ?? "대화를 선택하세요"}</h2></header>
        <div className="messages">
          {(active?.messages ?? []).map((message: Message) => (
            <article key={message.message_id} className={`message ${message.role}`}>
              {message.response_status && message.response_status !== "answer" && <span className={`status ${message.response_status}`}>{statusLabel[message.response_status]}</span>}
              <MessageContent content={message.content} />
              {!!message.sources?.length && <details><summary>정책 근거 {message.sources.length}개</summary>{message.sources.map((source) => <div className="source" key={source.source_id}><strong>{source.title}</strong><span>v{source.version_number} · {source.section_title}</span></div>)}</details>}
            </article>
          ))}
          {loading && <article className="message assistant" aria-live="polite"><p>근거를 확인하고 있습니다…</p></article>}
        </div>
        {active ? <form className="composer" onSubmit={submit}><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="정책, 상품 또는 리뷰에 대해 질문하세요." /><button className="primary" disabled={loading}>전송</button></form> : <div className="empty"><button className="primary" onClick={newConversation}>첫 대화 시작</button></div>}
        {error && <p className="error banner" role="alert">{error}</p>}
      </section>}
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
