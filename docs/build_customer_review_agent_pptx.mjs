import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const {
  SKILL_DIR,
  TMP_DIR,
  FINAL_PPTX,
  RUNTIME_PYTHON,
  WORKSPACE_DIR,
} = process.env;

for (const [name, value] of Object.entries({ SKILL_DIR, TMP_DIR, FINAL_PPTX, RUNTIME_PYTHON, WORKSPACE_DIR })) {
  if (!value || !path.isAbsolute(value)) throw new Error(`${name} must be an absolute path`);
}

const { finalizePresentation } = await import(
  pathToFileURL(path.join(SKILL_DIR, "container_tools/artifact_tool_utils.mjs")).href,
);

await fs.mkdir(TMP_DIR, { recursive: true });
await fs.mkdir(path.dirname(FINAL_PPTX), { recursive: true });

const W = 793.7008;
const H = 1122.5197;
const FONT = "Noto Sans KR";

const C = {
  ink: "#18231F",
  muted: "#66736D",
  line: "#DCE5E0",
  pale: "#F7F9F8",
  purple: "#6848A8",
  purpleSoft: "#F2EDFB",
  blue: "#2F6F9F",
  blueSoft: "#EDF6FC",
  orange: "#C96A1B",
  orangeSoft: "#FFF4E8",
  green: "#34735B",
  greenSoft: "#EDF7F2",
  white: "#FFFFFF",
};

const presentation = Presentation.create({ slideSize: { width: W, height: H } });
const slide = presentation.slides.add();
slide.background.fill = C.white;

function rect(x, y, w, h, fill, stroke = "none", radius = 0, strokeWidth = 0) {
  return slide.shapes.add({
    geometry: "rect",
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: stroke === "none" ? { fill: "none", width: 0 } : { style: "solid", fill: stroke, width: strokeWidth },
    ...(radius ? { borderRadius: radius } : {}),
  });
}

function textBox(text, x, y, w, h, size, color = C.ink, opts = {}) {
  const box = slide.shapes.add({
    geometry: "textbox",
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { fill: "none", width: 0 },
  });
  box.text = text;
  box.text.style = {
    typeface: FONT,
    fontSize: size,
    color,
    bold: opts.bold ?? false,
    alignment: opts.align ?? "left",
    verticalAlignment: opts.valign ?? "top",
    autoFit: opts.autoFit ?? "shrinkText",
    wrap: "square",
    insets: opts.insets ?? { top: 0, right: 0, bottom: 0, left: 0 },
    ...(opts.lineSpacing ? { lineSpacing: opts.lineSpacing } : {}),
  };
  return box;
}

function stepCircle(n, x, y, accent) {
  const s = slide.shapes.add({
    geometry: "ellipse",
    position: { left: x, top: y, width: 27, height: 27 },
    fill: accent,
    line: { fill: "none", width: 0 },
  });
  s.text = String(n);
  s.text.style = {
    typeface: FONT,
    fontSize: 13,
    bold: true,
    color: C.white,
    alignment: "center",
    verticalAlignment: "middle",
    autoFit: "none",
    insets: { top: 0, right: 0, bottom: 0, left: 0 },
  };
}

function node(x, y, w, h, accent, soft, badge, title, detail, strong = false) {
  const shape = rect(x, y, w, h, strong ? soft : C.white, accent, 9, strong ? 2.4 : 1.2);
  const badgeShape = slide.shapes.add({
    geometry: "ellipse",
    position: { left: x + 8, top: y + 8, width: 23, height: 23 },
    fill: soft,
    line: { style: "solid", fill: accent, width: 1 },
  });
  badgeShape.text = badge;
  badgeShape.text.style = {
    typeface: FONT,
    fontSize: badge.length > 2 ? 7 : 9,
    bold: true,
    color: accent,
    alignment: "center",
    verticalAlignment: "middle",
    autoFit: "shrinkText",
    wrap: "none",
    insets: { top: 0, right: 1, bottom: 0, left: 1 },
  };
  textBox(title, x + 36, y + 9, w - 43, 22, 10.8, C.ink, { bold: true, valign: "middle" });
  textBox(detail, x + 10, y + 39, w - 20, h - 45, 8.4, C.muted, { align: "center", valign: "middle" });
  return shape;
}

function connect(a, b, accent) {
  return slide.shapes.connect(a, b, {
    kind: "straight",
    fromSide: "right",
    toSide: "left",
    line: { style: "solid", fill: accent, width: 1.8 },
    tail: { type: "triangle", width: "sm", length: "sm" },
  });
}

function guard(text, x, y, w, accent, soft) {
  const g = rect(x, y, w, 22, soft, accent, 11, 1);
  g.text = text;
  g.text.style = {
    typeface: FONT,
    fontSize: 8.6,
    bold: true,
    color: accent,
    alignment: "center",
    verticalAlignment: "middle",
    autoFit: "shrinkText",
    insets: { top: 0, right: 6, bottom: 0, left: 6 },
  };
}

function band({ n, y, accent, soft, title, copy, nodes, guardText }) {
  const x = 42;
  const w = 710;
  const h = 128;
  const leftW = 191;
  rect(x, y, w, h, C.white, C.line, 11, 1);
  rect(x, y, leftW, h, soft, "none", 11, 0);
  rect(x + leftW - 4, y, 4, h, accent);
  stepCircle(n, x + 16, y + 15, accent);
  textBox(title, x + 51, y + 13, leftW - 62, 44, 14.2, C.ink, { bold: true, valign: "middle" });
  textBox(copy, x + 16, y + 67, leftW - 31, 47, 9.6, C.muted, { valign: "top", lineSpacing: 1.15 });

  const flowX = x + leftW + 18;
  const flowW = w - leftW - 36;
  const nodeY = y + 18;
  const nodeH = guardText ? 74 : 91;
  const gap = nodes.length === 4 ? 19 : 27;
  const nodeW = (flowW - gap * (nodes.length - 1)) / nodes.length;
  const shapes = nodes.map((item, idx) => node(
    flowX + idx * (nodeW + gap), nodeY, nodeW, nodeH,
    accent, soft, item.badge, item.title, item.detail, item.strong,
  ));
  for (let i = 0; i < shapes.length - 1; i += 1) connect(shapes[i], shapes[i + 1], accent);
  if (guardText) guard(guardText, flowX + 74, y + 99, flowW - 148, accent, soft);
}

textBox("CUSTOMER INTELLIGENCE", 42, 40, 710, 22, 12, C.green, { bold: true });
textBox("검증된 SQL과 Aspect 기반 고객 리뷰 분석 Agent", 42, 69, 710, 50, 35, C.ink, { bold: true, valign: "middle" });
textBox("LLM은 질문을 해석하고, 검증된 코드가 조회·검증·집계를 수행합니다.", 42, 124, 710, 24, 14, C.muted);
rect(42, 157, 710, 2, C.ink);

band({
  n: 1, y: 176, accent: C.blue, soft: C.blueSoft,
  title: "LLM의 SQL 생성 위험을 제거",
  copy: "Agent는 SQL을 직접 만들지 않고 사전에 구현하고 테스트한 Tool만 선택합니다.",
  guardText: "LLM 직접 SQL 생성 없음",
  nodes: [
    { badge: "Q", title: "사용자 질문", detail: "자연어 분석 요청" },
    { badge: "AI", title: "Agent Tool 선택", detail: "의도와 조건 해석" },
    { badge: "SQL", title: "검증된 SQL Tool", detail: "고정 Query와 입력 검증", strong: true },
    { badge: "DB", title: "PostgreSQL", detail: "리뷰 표본과 정량 통계" },
  ],
});

band({
  n: 2, y: 313, accent: C.purple, soft: C.purpleSoft,
  title: "리뷰를 Aspect 단위로 구조화",
  copy: "선별 리뷰에서 불만 유형과 판단 근거를 리뷰별 JSON으로 추출합니다.",
  nodes: [
    { badge: "TXT", title: "선별 리뷰", detail: "저평점과 고공감 표본" },
    { badge: "AI", title: "Aspect Extractor LLM", detail: "불만 유형과 감성 분석", strong: true },
    { badge: "{ }", title: "Aspect JSON", detail: "Topic, Sentiment, Evidence" },
  ],
});

band({
  n: 3, y: 450, accent: C.orange, soft: C.orangeSoft,
  title: "원문 검증 후 반복 불만을 정량화",
  copy: "LLM 결과를 그대로 사용하지 않고 Python 코드로 검증하고 집계합니다.",
  guardText: "원문에 존재하는 근거만 유지",
  nodes: [
    { badge: "{ }", title: "Aspect JSON", detail: "리뷰별 추출 결과" },
    { badge: "✓", title: "원문 근거 검증", detail: "없는 Evidence 제거", strong: true },
    { badge: "Py", title: "Python 집계", detail: "중복 제거와 빈도 계산" },
    { badge: "#", title: "구조화 결과", detail: "Aspect, 빈도, 비율, 근거" },
  ],
});

band({
  n: 4, y: 587, accent: C.green, soft: C.greenSoft,
  title: "구조화 결과를 Agent 판단 근거로 활용",
  copy: "정량 통계와 검증된 Evidence를 최종 LLM 입력으로 제공합니다.",
  nodes: [
    { badge: "CTX", title: "Grounded Context", detail: "SQL 통계와 Aspect Pattern" },
    { badge: "AI", title: "Final Agent LLM", detail: "검증 결과 기반 해석", strong: true },
    { badge: "ANS", title: "업무 활용 답변", detail: "반복 불만과 개선 우선순위" },
  ],
});

rect(42, 742, 710, 2, C.ink);
textBox("구현 방식", 42, 760, 710, 28, 17, C.ink, { bold: true });

function note(n, x, y, title, body, accent) {
  const marker = rect(x, y + 1, 27, 27, C.ink, "none", 7, 0);
  marker.text = n;
  marker.text.style = {
    typeface: FONT, fontSize: 9, bold: true, color: C.white,
    alignment: "center", verticalAlignment: "middle", autoFit: "none",
    insets: { top: 0, right: 0, bottom: 0, left: 0 },
  };
  textBox(title, x + 38, y, 292, 22, 11.2, accent, { bold: true, valign: "middle" });
  textBox(body, x + 38, y + 25, 292, 54, 9.4, C.ink, { valign: "top", lineSpacing: 1.12 });
}

note("01", 42, 802, "결정론적 SQL 조회",
  "Agent가 검증된 SQL Tool을 선택해 리뷰 표본과 통계를 조회합니다. LLM의 임의 SQL 생성을 차단해 집계 오류를 줄였습니다.", C.blue);
note("02", 404, 802, "Aspect Term 추출",
  "Extractor LLM이 리뷰별 불만 유형과 감성, 직접 경험 여부, 근거 문장을 구조화된 JSON으로 반환합니다.", C.purple);
note("03", 42, 895, "원문 검증과 Python 집계",
  "Evidence가 리뷰 원문에 실제 존재하는지 확인한 뒤 Aspect별 빈도와 표본 내 비율, 대표 근거를 계산합니다.", C.orange);
note("04", 404, 895, "Grounded Agent 답변",
  "최종 Agent는 검증된 통계와 리뷰 근거만 입력받아 반복 불만과 제품 개선 우선순위를 설명합니다.", C.green);

rect(42, 1000, 710, 67, C.purpleSoft, "none", 9, 0);
rect(42, 1000, 5, 67, C.purple);
textBox("핵심 설계", 61, 1013, 87, 20, 11, C.purple, { bold: true, valign: "middle" });
textBox("LLM에는 질문 해석과 의미 분류를 맡기고, 수치 조회·근거 검증·집계는 테스트 가능한 코드로 통제했습니다.",
  148, 1009, 584, 44, 11.3, C.ink, { bold: true, valign: "middle", lineSpacing: 1.1 });
textBox("Customer Intelligence · Review Analysis Agent", 42, 1084, 710, 16, 8.5, C.muted, { align: "right" });

slide.speakerNotes.textFrame.setText(
  "고객 리뷰 분석 Agent의 핵심 흐름. 모든 요소는 PowerPoint에서 편집 가능한 도형과 텍스트로 구성했다.",
);

const candidatePath = path.join(TMP_DIR, "customer_review_agent_candidate.pptx");
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);

const preview = await presentation.export({ slide, format: "png", scale: 1.5 });
await fs.writeFile(path.join(TMP_DIR, "customer_review_agent_preview.png"), new Uint8Array(await preview.arrayBuffer()));
const layout = await slide.export({ format: "layout" });
await fs.writeFile(path.join(TMP_DIR, "customer_review_agent_layout.json"), await layout.text());

const stagingDir = path.join(WORKSPACE_DIR, ".codex-finalizer");
await fs.mkdir(stagingDir, { recursive: true });
const stagedCandidate = path.join(stagingDir, "customer_review_agent_candidate.pptx");
await fs.copyFile(candidatePath, stagedCandidate);

await finalizePresentation({
  explicitTotalSlideCount: 1,
  requiredNativeTableOwnerSlides: [],
  requiredNativeChartOwnerSlides: [],
  workspaceDir: WORKSPACE_DIR,
  candidatePath: stagedCandidate,
  finalPath: FINAL_PPTX,
  pythonExecutable: RUNTIME_PYTHON,
  integrityValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_layout_geometry.py"),
  layoutArgs: [
    "--expected-slide-size-emu", "7560000,10692000",
    "--validate-bullet-geometry",
    "--validate-heading-fit",
  ],
  fontPolicy: { basis: "design", families: [FONT], scriptFonts: { ea: FONT } },
  verifyArtifactToolImport: true,
  receiptPath: path.join(stagingDir, `${path.basename(FINAL_PPTX)}.validation.json`),
});

console.log(FINAL_PPTX);
