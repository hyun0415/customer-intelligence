"use client";

import { Conversation, User } from "../lib/api";

type Props = {
  user: User;
  conversations: Conversation[];
  onOpenConversation: (conversationId: string) => void;
  onOpenProducts: () => void;
  onStartPolicyConversation: (question: string) => Promise<void>;
};

const policyQuestions = [
  "환불 승인 기준과 필요한 증빙을 알려줘.",
  "재배송이 가능한 조건과 처리 기한을 알려줘.",
  "고객 보상 시 중복 보상 제한과 승인 권한을 알려줘.",
  "의료·안전 문제가 접수됐을 때 처리 절차를 알려줘.",
];

function scopeLabel(value: string) {
  const sentinels: Record<string, string> = {
    ALL_COLLECTIONS: "전체 Collection",
    ALL_JURISDICTIONS: "전체 관할",
    ALL_DEPARTMENTS: "전체 부서",
  };
  return sentinels[value] ?? value.replaceAll("_", " ");
}

export function HomeDashboard({
  user,
  conversations,
  onOpenConversation,
  onOpenProducts,
  onStartPolicyConversation,
}: Props) {
  const canSearchPolicy = user.policy_scopes.length > 0;
  const recent = conversations.slice(0, 5);

  return (
    <section className="home-panel">
      <header className="home-header">
        <div>
          <p className="eyebrow">WORKSPACE</p>
          <h1>{user.display_name}님, 무엇을 확인할까요?</h1>
          <p className="muted">고객 리뷰 분석과 승인된 정책 검색을 업무 목적에 맞게 시작하세요.</p>
        </div>
      </header>

      <div className="home-content">
        <section className="start-grid" aria-label="업무 시작">
          <article className="start-card product-start-card">
            <span className="start-card-number">01</span>
            <div>
              <p className="section-kicker">REVIEW INTELLIGENCE</p>
              <h2>상품 리뷰 분석</h2>
              <p>상품명이나 ASIN을 선택해 평점, 저평점 리뷰와 반복 불만을 확인합니다.</p>
            </div>
            <button className="primary" onClick={onOpenProducts}>상품 찾기</button>
          </article>

          <article className="start-card policy-start-card">
            <span className="start-card-number">02</span>
            <div>
              <p className="section-kicker">POLICY ASSISTANT</p>
              <h2>정책 문의</h2>
              <p>허용된 범위의 최신 정책만 검색하고 근거가 부족하거나 충돌하면 이를 명시합니다.</p>
            </div>
            <button
              className="primary"
              disabled={!canSearchPolicy}
              onClick={() => onStartPolicyConversation("")}
            >
              정책 질문 시작
            </button>
          </article>
        </section>

        <section className="home-grid">
          <article className="home-card policy-entry-card">
            <div className="home-card-heading">
              <div>
                <p className="section-kicker">QUICK QUESTIONS</p>
                <h2>자주 묻는 정책</h2>
              </div>
              <span className={canSearchPolicy ? "access-badge" : "access-badge denied"}>
                {canSearchPolicy ? "검색 가능" : "권한 없음"}
              </span>
            </div>
            <div className="policy-question-grid">
              {policyQuestions.map((question) => (
                <button
                  key={question}
                  disabled={!canSearchPolicy}
                  onClick={() => onStartPolicyConversation(question)}
                >
                  {question}
                  <span aria-hidden="true">→</span>
                </button>
              ))}
            </div>
            <div className="scope-summary">
              <strong>현재 적용되는 정책 범위</strong>
              {canSearchPolicy ? (
                <div className="scope-list">
                  {user.policy_scopes.map((scope, index) => (
                    <span key={`${scope.collection}-${scope.jurisdiction}-${scope.department}-${index}`}>
                      {scopeLabel(scope.collection)} · {scopeLabel(scope.jurisdiction)} · {scopeLabel(scope.department)}
                    </span>
                  ))}
                </div>
              ) : (
                <p>관리자가 정책 검색 범위를 부여한 뒤 사용할 수 있습니다.</p>
              )}
              <small>표시된 범위는 안내용이며 실제 접근 범위는 서버에서 강제됩니다.</small>
            </div>
          </article>

          <article className="home-card recent-card">
            <div className="home-card-heading">
              <div>
                <p className="section-kicker">RECENT WORK</p>
                <h2>최근 대화</h2>
              </div>
              <span className="conversation-count">{conversations.length}개</span>
            </div>
            <div className="recent-list">
              {recent.length === 0 && (
                <p className="muted">아직 저장된 대화가 없습니다.</p>
              )}
              {recent.map((conversation) => (
                <button
                  key={conversation.conversation_id}
                  onClick={() => onOpenConversation(conversation.conversation_id)}
                >
                  <span className={`context-mark ${conversation.context_mode}`}>
                    {conversation.context_mode === "product" ? "상품" : "일반"}
                  </span>
                  <span className="recent-title">
                    <strong>{conversation.title}</strong>
                    <small>
                      {conversation.context_mode === "product"
                        ? `${conversation.product_store || "상품"} · ${conversation.product_parent_asin}`
                        : new Date(conversation.updated_at).toLocaleString("ko-KR")}
                    </small>
                  </span>
                  <span aria-hidden="true">→</span>
                </button>
              ))}
            </div>
          </article>
        </section>
      </div>
    </section>
  );
}
