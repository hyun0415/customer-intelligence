"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, Conversation, Message, User } from "../lib/api";
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

  async function loadConversations() {
    const rows = await api<Conversation[]>("/api/conversations");
    setConversations(rows);
    if (rows.length && !active) await openConversation(rows[0].conversation_id);
  }

  async function openConversation(id: string) {
    setActive(await api<Conversation>(`/api/conversations/${id}`));
  }

  useEffect(() => {
    api<{ oidc_enabled: boolean; dev_login_enabled: boolean; oidc_provider: string }>("/api/auth/config").then(setAuthConfig).catch(() => undefined);
    api<User>("/api/auth/me")
      .then((value) => {
        setUser(value);
        return api<Conversation[]>("/api/conversations");
      })
      .then(setConversations)
      .catch(() => setUser(null));
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
      setError(reason instanceof Error ? reason.message : "로그인 실패");
    }
  }

  async function newConversation() {
    const created = await api<Conversation>("/api/conversations", {
      method: "POST",
      body: JSON.stringify({ title: "새 대화" }),
    });
    setConversations((items) => [created, ...items]);
    setActive({ ...created, messages: [] });
  }

  async function logout() {
    setError("");
    try {
      await api<void>("/api/auth/logout", { method: "POST" });
      setUser(null);
      setConversations([]);
      setActive(null);
      setQuestion("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "로그아웃 실패");
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
      setError(reason instanceof Error ? reason.message : "답변 생성 실패");
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
          <button className="logout" onClick={logout}>로그아웃</button>
        </div>
        <button className="primary" onClick={newConversation}>+ 새 대화</button>
        <nav>
          {conversations.map((conversation) => (
            <button className={active?.conversation_id === conversation.conversation_id ? "active" : ""} key={conversation.conversation_id} onClick={() => openConversation(conversation.conversation_id)}>
              {conversation.title}
            </button>
          ))}
        </nav>
      </aside>
      <section className="chat-panel">
        <header><h2>{active?.title ?? "대화를 선택하세요"}</h2></header>
        <div className="messages">
          {(active?.messages ?? []).map((message: Message) => (
            <article key={message.message_id} className={`message ${message.role}`}>
              {message.response_status && message.response_status !== "answer" && <span className={`status ${message.response_status}`}>{statusLabel[message.response_status]}</span>}
              <MessageContent content={message.content} />
              {!!message.sources?.length && <details><summary>정책 근거 {message.sources.length}개</summary>{message.sources.map((source) => <div className="source" key={source.source_id}><strong>{source.title}</strong><span>v{source.version_number} · {source.section_title}</span></div>)}</details>}
            </article>
          ))}
          {loading && <article className="message assistant"><p>근거를 확인하고 있습니다…</p></article>}
        </div>
        {active ? <form className="composer" onSubmit={submit}><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="정책, 상품 또는 리뷰에 대해 질문하세요." /><button className="primary" disabled={loading}>전송</button></form> : <div className="empty"><button className="primary" onClick={newConversation}>첫 대화 시작</button></div>}
        {error && <p className="error banner">{error}</p>}
      </section>
    </main>
  );
}
