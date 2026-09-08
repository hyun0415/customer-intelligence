"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  api,
  AspectJob,
  DashboardProduct,
  DashboardProductDetail,
  ReviewPatternResult,
} from "../lib/api";
import { CheckIcon, SearchIcon } from "./Icons";

type Props = {
  onError: (message: string) => void;
  errorMessage: (reason: unknown, fallback: string) => string;
  onStartProductConversation: (product: DashboardProduct) => Promise<void>;
};

function formatNumber(value: number) {
  return new Intl.NumberFormat("ko-KR").format(value);
}

function StarIcon() {
  return <span aria-hidden="true">★</span>;
}

export function Dashboard({ onError, errorMessage, onStartProductConversation }: Props) {
  const [products, setProducts] = useState<DashboardProduct[]>([]);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<DashboardProductDetail | null>(null);
  const [patterns, setPatterns] = useState<ReviewPatternResult | null>(null);
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [patternLoading, setPatternLoading] = useState(false);
  const [patternJobId, setPatternJobId] = useState("");

  async function loadDetail(parentAsin: string) {
    setLoading(true);
    setPatterns(null);
    onError("");
    try {
      const row = await api<DashboardProductDetail>(
        `/api/dashboard/products/${encodeURIComponent(parentAsin)}`,
      );
      setSelected(parentAsin);
      setDetail(row);
      window.sessionStorage.setItem("ci:dashboard-product", parentAsin);
      const savedJob = window.sessionStorage.getItem(`ci:aspect-job:${parentAsin}`) ?? "";
      setPatternJobId(savedJob);
      setPatternLoading(Boolean(savedJob));
    } catch (reason) {
      onError(errorMessage(reason, "상품 분석 정보를 불러오지 못했습니다."));
    } finally {
      setLoading(false);
    }
  }

  async function loadProducts(search = "") {
    setLoading(true);
    onError("");
    try {
      const rows = await api<DashboardProduct[]>(
        `/api/dashboard/products?limit=12&query=${encodeURIComponent(search)}`,
      );
      setProducts(rows);
      if (rows.length) {
        const savedProduct = search
          ? null
          : window.sessionStorage.getItem("ci:dashboard-product");
        const targetProduct = rows.some(
          (row) => row.parent_asin === savedProduct,
        )
          ? savedProduct!
          : rows[0].parent_asin;
        await loadDetail(targetProduct);
      } else {
        setSelected("");
        setDetail(null);
        setLoading(false);
      }
    } catch (reason) {
      setLoading(false);
      onError(errorMessage(reason, "Dashboard를 불러오지 못했습니다."));
    }
  }

  useEffect(() => {
    loadProducts();
  }, []);

  useEffect(() => {
    if (!patternJobId) return;
    let stopped = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const job = await api<AspectJob>(`/api/dashboard/pattern-jobs/${patternJobId}`);
        if (stopped) return;
        if (job.status === "succeeded" && job.result) {
          setPatterns(job.result);
          setPatternLoading(false);
          setPatternJobId("");
          window.sessionStorage.removeItem(`ci:aspect-job:${job.parent_asin}`);
          return;
        }
        if (job.status === "failed") {
          setPatternLoading(false);
          setPatternJobId("");
          window.sessionStorage.removeItem(`ci:aspect-job:${job.parent_asin}`);
          onError(job.error || "Aspect 분석을 완료하지 못했습니다.");
          return;
        }
        timer = window.setTimeout(poll, 1500);
      } catch (reason) {
        if (stopped) return;
        setPatternLoading(false);
        setPatternJobId("");
        window.sessionStorage.removeItem(`ci:aspect-job:${selected}`);
        onError(errorMessage(reason, "Aspect 분석 상태를 확인하지 못했습니다."));
      }
    };
    poll();
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [patternJobId, selected, errorMessage, onError]);

  async function search(event: FormEvent) {
    event.preventDefault();
    const normalized = query.trim();
    setAppliedQuery(normalized);
    await loadProducts(normalized);
  }

  async function clearSearch() {
    setQuery("");
    setAppliedQuery("");
    await loadProducts();
  }

  async function analyzePatterns() {
    if (!selected || patternLoading) return;
    setPatternLoading(true);
    onError("");
    try {
      const job = await api<AspectJob>(
        `/api/dashboard/products/${encodeURIComponent(selected)}/patterns`,
        { method: "POST" },
      );
      window.sessionStorage.setItem(`ci:aspect-job:${selected}`, job.job_id);
      setPatternJobId(job.job_id);
    } catch (reason) {
      setPatternLoading(false);
      onError(errorMessage(reason, "Aspect 분석을 완료하지 못했습니다."));
    }
  }

  const maximumRatingCount = Math.max(
    1,
    ...(detail?.rating_distribution.map((item) => item.review_count) ?? [1]),
  );

  return (
    <section className="dashboard-panel">
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">REVIEW INTELLIGENCE</p>
          <h2>고객 리뷰 Dashboard</h2>
          <p className="muted">검증된 SQL 집계와 리뷰 원문을 함께 확인합니다.</p>
        </div>
        <form className="dashboard-search" onSubmit={search}>
          <label className="sr-only" htmlFor="product-search">상품 검색</label>
          <div className="search-field">
            <SearchIcon />
            <input
              id="product-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="상품명, 브랜드 또는 ASIN"
            />
            {query && <button className="search-clear" type="button" onClick={clearSearch} aria-label="검색어 지우기" title="검색어 지우기">×</button>}
          </div>
          <button className="search-submit" type="submit" disabled={loading}>{loading ? "확인 중" : "검색"}</button>
        </form>
      </header>

      <div className="dashboard-content">
        {!loading && (
          <div className="search-summary" role="status">
            <div>
              <strong>{appliedQuery ? `“${appliedQuery}” 검색 결과` : "분석 가능한 상품"}</strong>
              <span>{products.length}개 상품</span>
            </div>
            {appliedQuery && <button type="button" onClick={clearSearch}>전체 상품 보기</button>}
          </div>
        )}
        {products.length > 0 && (
          <section className="product-strip" aria-label="분석할 상품 선택">
            {products.map((product) => (
              <button
                type="button"
                key={product.parent_asin}
                className={selected === product.parent_asin ? "active" : ""}
                aria-pressed={selected === product.parent_asin}
                onClick={() => loadDetail(product.parent_asin)}
              >
                <div className="product-result-heading">
                  <span className="product-result-store">{product.store || "브랜드 미상"}</span>
                  {selected === product.parent_asin && <span className="selected-product-badge"><CheckIcon /> 선택됨</span>}
                </div>
                <strong className="product-result-title">{product.title}</strong>
                <span className="product-result-asin">ASIN {product.parent_asin}</span>
                <div className="product-result-metrics">
                  <span><StarIcon /> {product.average_rating?.toFixed(2) ?? "-"}</span>
                  <span>리뷰 {formatNumber(product.review_count)}개</span>
                  <span className="negative">1~3점 {product.negative_ratio.toFixed(1)}%</span>
                </div>
              </button>
            ))}
          </section>
        )}

        {loading && !detail && (
          <div className="dashboard-empty" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            <p>리뷰 데이터를 불러오고 있습니다.</p>
          </div>
        )}

        {!loading && !detail && (
          <div className="dashboard-empty">
            <strong>검색 결과가 없습니다.</strong>
            <p className="muted">다른 상품명이나 ASIN으로 검색해 보세요.</p>
          </div>
        )}

        {detail && (
          <>
            <div className="product-heading">
              <div>
                <span className="product-store">{detail.store || "브랜드 미상"}</span>
                <h3>{detail.title}</h3>
                <p className="muted small">{detail.parent_asin}</p>
              </div>
              <div className="product-actions">
                {loading && <span className="loading-label"><span className="spinner" /> 갱신 중</span>}
                <button className="primary" onClick={() => onStartProductConversation(detail)}>이 상품으로 대화하기</button>
              </div>
            </div>

            <section className="metric-grid" aria-label="핵심 리뷰 지표">
              <article>
                <span>평균 평점</span>
                <strong><StarIcon /> {detail.average_rating?.toFixed(2) ?? "-"}</strong>
                <small>5점 만점</small>
              </article>
              <article>
                <span>분석 리뷰</span>
                <strong>{formatNumber(detail.review_count)}</strong>
                <small>현재 DB 표본</small>
              </article>
              <article className="warning-metric">
                <span>1~3점 리뷰</span>
                <strong>{detail.negative_ratio.toFixed(1)}%</strong>
                <small>{formatNumber(detail.negative_count)}건</small>
              </article>
              <article>
                <span>구매 인증</span>
                <strong>{detail.verified_ratio.toFixed(1)}%</strong>
                <small>{formatNumber(detail.verified_count)}건</small>
              </article>
            </section>

            <section className="dashboard-grid">
              <article className="dashboard-card rating-card">
                <div className="card-heading">
                  <div>
                    <p className="section-kicker">DISTRIBUTION</p>
                    <h3>평점 분포</h3>
                  </div>
                  <span className="method-badge">SQL 집계</span>
                </div>
                <div className="rating-bars">
                  {detail.rating_distribution.map((item) => (
                    <div className="rating-row" key={item.rating}>
                      <span>{item.rating}점</span>
                      <div className="bar-track">
                        <div
                          className={`bar-fill rating-${item.rating}`}
                          style={{ width: `${(item.review_count / maximumRatingCount) * 100}%` }}
                        />
                      </div>
                      <strong>{formatNumber(item.review_count)}</strong>
                    </div>
                  ))}
                </div>
              </article>

              <article className="dashboard-card aspect-card">
                <div className="card-heading">
                  <div>
                    <p className="section-kicker">ASPECT PATTERNS</p>
                    <h3>반복 불만 유형</h3>
                  </div>
                  {patterns && <span className="method-badge">표본 {patterns.sample_size}건</span>}
                </div>
                {!patterns && !patternLoading && (
                  <div className="aspect-prompt">
                    <p>공감표가 있는 1~3점 리뷰 최대 20건에서 Aspect와 원문 근거를 추출합니다.</p>
                    <button className="primary" onClick={analyzePatterns}>Aspect 분석 실행</button>
                    <small>LLM 호출이 발생하므로 선택한 상품에서만 실행합니다.</small>
                  </div>
                )}
                {patternLoading && (
                  <div className="aspect-prompt" aria-live="polite">
                    <span className="spinner large" aria-hidden="true" />
                    <strong>불만 유형과 원문 근거를 확인하고 있습니다.</strong>
                    <small>추출 후 Python으로 근거와 빈도를 검증·집계합니다.</small>
                  </div>
                )}
                {patterns && patterns.patterns.length === 0 && (
                  <p className="muted">검증 기준을 통과한 반복 불만이 없습니다.</p>
                )}
                {patterns && patterns.patterns.length > 0 && (
                  <div className="aspect-bars">
                    {patterns.patterns.slice(0, 6).map((pattern) => (
                      <details className="aspect-row" key={pattern.topic}>
                        <summary>
                          <span className="aspect-label">{pattern.label}</span>
                          <div className="bar-track"><div className="bar-fill aspect-fill" style={{ width: `${pattern.ratio * 100}%` }} /></div>
                          <strong>{(pattern.ratio * 100).toFixed(1)}%</strong>
                        </summary>
                        <div className="aspect-evidence">
                          <p>{pattern.description}</p>
                          <p className="muted small">{pattern.count}건 · 표본 내 비율 · 평균 신뢰도 {(pattern.average_confidence * 100).toFixed(0)}%</p>
                          {pattern.evidence.slice(0, 2).map((item, index) => (
                            <blockquote key={`${item.source_index}-${index}`}>“{item.evidence}”</blockquote>
                          ))}
                        </div>
                      </details>
                    ))}
                  </div>
                )}
              </article>
            </section>

            <section className="dashboard-card comparison-card">
              <div className="card-heading">
                <div>
                  <p className="section-kicker">PRODUCT COMPARISON</p>
                  <h3>리뷰 규모와 저평점 비율 비교</h3>
                </div>
                <span className="method-badge">검색 결과 기준</span>
              </div>
              <div className="table-scroll">
                <table>
                  <thead><tr><th>상품</th><th>평균 평점</th><th>리뷰</th><th>1~3점 비율</th><th>구매 인증</th></tr></thead>
                  <tbody>
                    {products.slice(0, 8).map((product) => (
                      <tr className={product.parent_asin === selected ? "selected" : ""} key={product.parent_asin}>
                        <td><button className="table-product-button" onClick={() => loadDetail(product.parent_asin)}><strong>{product.title}</strong><span>{product.store || product.parent_asin}</span></button></td>
                        <td>{product.average_rating?.toFixed(2) ?? "-"}</td>
                        <td>{formatNumber(product.review_count)}</td>
                        <td><span className="negative-pill">{product.negative_ratio.toFixed(1)}%</span></td>
                        <td>{product.verified_ratio.toFixed(1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="dashboard-card evidence-card">
              <div className="card-heading">
                <div>
                  <p className="section-kicker">REVIEW EVIDENCE</p>
                  <h3>공감도가 높은 저평점 리뷰</h3>
                </div>
                <span className="method-badge">1~3점 · 최대 5건</span>
              </div>
              <div className="review-grid">
                {detail.representative_reviews.length === 0 && (
                  <p className="muted">이 상품에는 표시할 1~3점 리뷰가 없습니다.</p>
                )}
                {detail.representative_reviews.map((review) => (
                  <article key={review.review_id}>
                    <div className="review-meta">
                      <span className="review-evidence-label">대표 근거 리뷰</span>
                      <span className="review-rating"><StarIcon /> {review.rating}</span>
                      <span>공감 {formatNumber(review.helpful_vote)}</span>
                      {review.verified_purchase && <span>구매 인증</span>}
                    </div>
                    <strong title={review.review_title || "제목 없는 리뷰"}>{review.review_title || "제목 없는 리뷰"}</strong>
                    <p title={review.review_text || "리뷰 본문이 없습니다."}>{review.review_text || "리뷰 본문이 없습니다."}</p>
                  </article>
                ))}
              </div>
            </section>
          </>
        )}
      </div>
    </section>
  );
}
