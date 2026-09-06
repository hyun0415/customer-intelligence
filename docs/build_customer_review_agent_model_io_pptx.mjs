import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const { SKILL_DIR, TMP_DIR, FINAL_PPTX, RUNTIME_PYTHON, WORKSPACE_DIR } = process.env;
for (const [key, value] of Object.entries({ SKILL_DIR, TMP_DIR, FINAL_PPTX, RUNTIME_PYTHON, WORKSPACE_DIR })) {
  if (!value || !path.isAbsolute(value)) throw new Error(`${key} must be an absolute path`);
}

const { finalizePresentation } = await import(
  pathToFileURL(path.join(SKILL_DIR, "container_tools/artifact_tool_utils.mjs")).href,
);

await fs.mkdir(TMP_DIR, { recursive: true });
await fs.mkdir(path.dirname(FINAL_PPTX), { recursive: true });

const FONT = "Noto Sans KR";
const W = 1280;
const H = 720;
const C = {
  ink: "#17231F",
  muted: "#64716B",
  line: "#D8E3DE",
  white: "#FFFFFF",
  stage: "#FBFCFB",
  input: "#F7F9F8",
  inputLine: "#8B9892",
  model: "#F1ECFB",
  modelLine: "#6B4BB2",
  output: "#EDF7F2",
  outputLine: "#2F765B",
  code: "#EDF6FC",
  codeLine: "#2E6F9F",
  accent: "#27664F",
};

const icons = {
  input: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#68756F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h10l4 4v12H4z"/><path d="M14 4v4h4M8 13h8M8 17h5"/></g></svg>`,
  ai: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#6B4BB2" stroke-width="1.8" stroke-linecap="round"><circle cx="7" cy="7" r="2"/><circle cx="17" cy="7" r="2"/><circle cx="12" cy="17" r="2"/><path d="M9 7h6M8.2 8.5l2.8 6.7M15.8 8.5 13 15.2"/></g></svg>`,
  tool: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#2F765B" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M7 6v12M4 18h16"/><path d="M11 10h6M11 14h4"/></g></svg>`,
  db: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#2E6F9F" stroke-width="1.8" stroke-linecap="round"><ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v7c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 12v7c0 1.7 3.1 3 7 3s7-1.3 7-3v-7"/></g></svg>`,
  json: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#2F765B" stroke-width="1.8" stroke-linecap="round"><path d="M8 4C5 4 5 7 5 9s-1 3-3 3c2 0 3 1 3 3s0 5 3 5M16 4c3 0 3 3 3 5s1 3 3 3c-2 0-3 1-3 3s0 5-3 5"/></g></svg>`,
  check: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#2E6F9F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4 6v6c0 5 3.4 8 8 9 4.6-1 8-4 8-9V6z"/><path d="m8.5 12 2.2 2.2 4.8-5"/></g></svg>`,
  answer: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#2F765B" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 5h14v11H9l-4 4z"/><path d="M8 9h8M8 13h5"/></g></svg>`,
};

function svgDataUrl(svg) {
  return `data:image/svg+xml;base64,${Buffer.from(svg, "utf8").toString("base64")}`;
}

const presentation = Presentation.create({ slideSize: { width: W, height: H } });
const slide = presentation.slides.add();
slide.background.fill = C.white;

function rect(x, y, w, h, fill, line = "none", radius = 0, width = 0) {
  return slide.shapes.add({
    geometry: "rect",
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: line === "none" ? { fill: "none", width: 0 } : { style: "solid", fill: line, width },
    ...(radius ? { borderRadius: radius } : {}),
  });
}

function textBox(text, x, y, w, h, size, color = C.ink, opts = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = {
    typeface: FONT,
    fontSize: size,
    color,
    bold: opts.bold ?? false,
    alignment: opts.align ?? "left",
    verticalAlignment: opts.valign ?? "top",
    autoFit: opts.autoFit ?? "shrinkText",
    wrap: "square",
    insets: opts.insets ?? { top: 0, right: 0, bottom: 0, left: 0 },
  };
  return shape;
}

function addIcon(iconName, x, y, size = 28) {
  rect(x - 7, y - 7, size + 14, size + 14, "#FFFFFF", "none", 10, 0);
  slide.images.add({
    dataUrl: svgDataUrl(icons[iconName]),
    alt: `${iconName} pictogram`,
    fit: "contain",
    position: { left: x, top: y, width: size, height: size },
  });
}

function badge(label, x, y, color, width) {
  const b = rect(x, y, width, 19, "#FFFFFF", color, 9, 0.9);
  b.text = label;
  b.text.style = {
    typeface: FONT, fontSize: 8.2, bold: true, color,
    alignment: "center", verticalAlignment: "middle", autoFit: "shrinkText",
    wrap: "none", insets: { top: 0, right: 3, bottom: 0, left: 3 },
  };
}

function node({ x, y, w, h, type, icon, label, title, detail, badges = [], code = false }) {
  const map = {
    input: [C.input, C.inputLine],
    model: [C.model, C.modelLine],
    output: [C.output, C.outputLine],
    code: [C.code, C.codeLine],
  };
  const [fill, line] = map[type];
  rect(x, y, w, h, fill, line, 12, type === "model" ? 2.5 : 1.2);
  addIcon(icon, x + 18, y + 26, 25);
  const tx = x + 65;
  textBox(label, tx, y + 11, w - 78, 14, 8.8, C.muted, { bold: true, valign: "middle" });
  textBox(title, tx, y + 29, w - 78, code ? 21 : 25, code ? 10.5 : 13.5, C.ink, { bold: true, valign: "middle" });
  textBox(detail, tx, y + 55, w - 78, h - 59, 9.6, C.muted, { valign: "top" });
  const badgeTotal = badges.reduce((sum, item) => sum + item.width, 0) + Math.max(0, badges.length - 1) * 6;
  let bx = x + w - 13 - badgeTotal;
  for (const item of badges) {
    badge(item.label, bx, y + 8, item.color, item.width);
    bx += item.width + 6;
  }
}

function downArrow(cx, y, height = 17) {
  slide.shapes.add({
    geometry: "downArrow",
    position: { left: cx - 4, top: y, width: 8, height },
    fill: "#8B9992",
    line: { fill: "none", width: 0 },
  });
}

function bridge(x, y, label) {
  textBox(label, x - 8, y - 36, 78, 29, 9.4, C.muted, { bold: true, align: "center", valign: "bottom" });
  slide.shapes.add({
    geometry: "line",
    position: { left: x, top: y, width: 58, height: 0 },
    fill: "none",
    line: { style: "solid", fill: C.accent, width: 2.6 },
    tail: { type: "triangle", width: "med", length: "med" },
  });
}

textBox("CUSTOMER INTELLIGENCE", 52, 34, 1176, 20, 11.5, C.accent, { bold: true });
textBox("고객 리뷰 분석 Agent의 모델 입력과 출력", 52, 61, 1176, 44, 32, C.ink, { bold: true, valign: "middle" });
textBox("각 단계에서 모델이 받는 정보와 생성 결과를 분리하고, 조회·검증·집계는 테스트 가능한 코드로 통제했습니다.",
  52, 107, 1176, 24, 13.2, C.muted, { valign: "middle" });

const stageY = 151;
const stageW = 344;
const stageH = 485;
const xs = [52, 468, 884];

function stageFrame(x, n, title) {
  rect(x, stageY, stageW, stageH, C.stage, C.line, 16, 1);
  const step = slide.shapes.add({
    geometry: "ellipse",
    position: { left: x + 20, top: stageY + 18, width: 33, height: 33 },
    fill: C.ink,
    line: { fill: "none", width: 0 },
  });
  step.text = String(n);
  step.text.style = { typeface: FONT, fontSize: 13, bold: true, color: C.white, alignment: "center", verticalAlignment: "middle", autoFit: "none", insets: { top: 0, right: 0, bottom: 0, left: 0 } };
  textBox(title, x + 65, stageY + 19, stageW - 84, 31, 17.2, C.ink, { bold: true, valign: "middle" });
}

stageFrame(xs[0], 1, "Tool 호출과 리뷰 조회");
stageFrame(xs[1], 2, "Tool 내부 분석");
stageFrame(xs[2], 3, "최종 답변 생성");

const nx = xs.map(x => x + 22);
const nw = 300;
const y1 = 220;
const nh = 82;
const arrowGap = 19;
const y2 = y1 + nh + arrowGap;
const y3 = y2 + nh + arrowGap;
const y4 = y3 + nh + arrowGap;

node({ x: nx[0], y: y1, w: nw, h: nh, type: "input", icon: "input", label: "INPUT", title: "“이 상품의 반복 불만과\n개선점을 알려줘”", detail: "사용자 질문과 대화 맥락" });
downArrow(nx[0] + nw / 2, y1 + nh + 1, 16);
node({ x: nx[0], y: y2, w: nw, h: nh, type: "model", icon: "ai", label: "MODEL", title: "Agent LLM", detail: "질문 의도와 조회 조건 해석", badges: [
  { label: "OpenAI API", color: "#111111", width: 67 }, { label: "LangGraph", color: "#5B3DA1", width: 65 },
] });
downArrow(nx[0] + nw / 2, y2 + nh + 1, 16);
node({ x: nx[0], y: y3, w: nw, h: nh, type: "output", icon: "tool", label: "TOOL CALL", title: "get_review_patterns_tool", detail: "parent_asin · limit=20", code: true });
downArrow(nx[0] + nw / 2, y3 + nh + 1, 16);
node({ x: nx[0], y: y4, w: nw, h: nh, type: "code", icon: "db", label: "TOOL INTERNAL", title: "검증된 SQL로 리뷰 조회", detail: "3점 이하·공감표 1 이상 표본 선별", badges: [
  { label: "PostgreSQL", color: "#336791", width: 72 },
] });

node({ x: nx[1], y: y1, w: nw, h: nh, type: "input", icon: "input", label: "TOOL INTERNAL INPUT", title: "조회된 리뷰 표본", detail: "리뷰 원문·평점·공감표\n추출 규칙·JSON Schema" });
downArrow(nx[1] + nw / 2, y1 + nh + 1, 16);
node({ x: nx[1], y: y2, w: nw, h: nh, type: "model", icon: "ai", label: "MODEL", title: "Aspect Extractor LLM", detail: "불만 유형과 감성, 근거 문장 식별", badges: [
  { label: "OpenAI API", color: "#111111", width: 67 },
] });
downArrow(nx[1] + nw / 2, y2 + nh + 1, 16);
node({ x: nx[1], y: y3, w: nw, h: nh, type: "output", icon: "json", label: "MODEL OUTPUT", title: "Aspect JSON", detail: "Aspect Term · Sentiment · Evidence" });
downArrow(nx[1] + nw / 2, y3 + nh + 1, 16);
node({ x: nx[1], y: y4, w: nw, h: nh, type: "output", icon: "check", label: "TOOL RESULT", title: "ReviewPatternResult", detail: "원문 검증 후 Aspect 빈도·표본 내 비율·근거", code: true, badges: [
  { label: "Python 집계", color: "#286DA8", width: 64 },
] });

node({ x: nx[2], y: y1, w: nw, h: nh, type: "input", icon: "input", label: "INPUT", title: "질문 + ReviewPatternResult", detail: "선정 기준·Aspect 빈도·표본 내 비율\n대표 리뷰 원문 근거" });
downArrow(nx[2] + nw / 2, y1 + nh + 1, 16);
node({ x: nx[2], y: y2, w: nw, h: nh, type: "model", icon: "ai", label: "MODEL", title: "Final Agent LLM", detail: "검증 결과를 업무 관점으로 해석", badges: [
  { label: "OpenAI API", color: "#111111", width: 67 },
] });
downArrow(nx[2] + nw / 2, y2 + nh + 1, 16);
node({ x: nx[2], y: y3, w: nw, h: nh, type: "output", icon: "answer", label: "FINAL OUTPUT", title: "업무 활용 답변", detail: "반복 불만·수치·대표 근거\n제품 개선 우선순위" });

bridge(401, 391, "조회된\n리뷰 표본");
bridge(817, 391, "구조화된\nTool 결과");

const legendY = 657;
const legend = [
  [C.input, "입력"], [C.model, "LLM"], [C.output, "모델 출력"], [C.code, "검증된 코드"],
];
let lx = 52;
for (const [fill, label] of legend) {
  rect(lx, legendY + 5, 11, 11, fill, C.line, 3, 0.5);
  textBox(label, lx + 17, legendY, 78, 22, 10.2, C.muted, { valign: "middle" });
  lx += 98;
}
textBox("LLM이 SQL을 직접 생성하지 않으며, 원문에 없는 Evidence는 집계 전에 제거합니다.", 670, legendY, 558, 22, 10.4, "#48564F", { bold: true, align: "right", valign: "middle" });

slide.speakerNotes.textFrame.setText(
  "기술 표기 참고: OpenAI API https://openai.com/brand/ ; LangGraph https://docs.langchain.com/ ; PostgreSQL https://wiki.postgresql.org/wiki/Logo ; Python https://www.python.org/community/logos/ . 제품 로고를 변형하지 않고, 도식에는 자체 제작한 중립 픽토그램과 공식 기술명을 사용했다.",
);

const candidatePath = path.join(TMP_DIR, "customer_review_agent_model_io_candidate.pptx");
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
const preview = await presentation.export({ slide, format: "png", scale: 1.4 });
await fs.writeFile(path.join(TMP_DIR, "customer_review_agent_model_io_preview.png"), new Uint8Array(await preview.arrayBuffer()));
const layout = await slide.export({ format: "layout" });
await fs.writeFile(path.join(TMP_DIR, "customer_review_agent_model_io_layout.json"), await layout.text());

const stagingDir = path.join(WORKSPACE_DIR, ".codex-finalizer");
await fs.mkdir(stagingDir, { recursive: true });
const stagedCandidate = path.join(stagingDir, "customer_review_agent_model_io_candidate.pptx");
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
    "--expected-slide-size-emu", "12192000,6858000",
    "--validate-bullet-geometry",
    "--validate-heading-fit",
  ],
  fontPolicy: { basis: "design", families: [FONT], scriptFonts: { ea: FONT } },
  verifyArtifactToolImport: true,
  receiptPath: path.join(stagingDir, `${path.basename(FINAL_PPTX)}.validation.json`),
});

console.log(FINAL_PPTX);
