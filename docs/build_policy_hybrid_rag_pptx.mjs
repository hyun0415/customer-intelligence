import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const { SKILL_DIR, TMP_DIR, FINAL_PPTX, RUNTIME_PYTHON, WORKSPACE_DIR } = process.env;
for (const [key, value] of Object.entries({ SKILL_DIR, TMP_DIR, FINAL_PPTX, RUNTIME_PYTHON, WORKSPACE_DIR })) {
  if (!value || !path.isAbsolute(value)) throw new Error(`${key} must be an absolute path`);
}
const { finalizePresentation } = await import(pathToFileURL(path.join(SKILL_DIR, "container_tools/artifact_tool_utils.mjs")).href);
await fs.mkdir(TMP_DIR, { recursive: true });
await fs.mkdir(path.dirname(FINAL_PPTX), { recursive: true });

const FONT = "Noto Sans KR";
const W = 1280;
const H = 720;
const C = {
  white: "#FFFFFF", ink: "#17231F", muted: "#64716B", line: "#D8E3DE", arrow: "#8B9992",
  green: "#27664F", greenBg: "#EDF7F2", blue: "#2E6F9F", blueBg: "#EDF6FC",
  violet: "#6B4BB2", violetBg: "#F1ECFB", amber: "#A56216", amberBg: "#FFF5E6",
  rose: "#A13C4A", roseBg: "#FFF0F2", grayBg: "#F7F9F8",
};

const icons = {
  question: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#68756F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 5h14v11H9l-4 4z"/><path d="M8 9h8M8 13h5"/></g></svg>`,
  shieldGreen: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#27664F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4 6v6c0 5 3.4 8 8 9 4.6-1 8-4 8-9V6z"/><path d="m8.5 12 2.2 2.2 4.8-5"/></g></svg>`,
  shieldViolet: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#6B4BB2" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4 6v6c0 5 3.4 8 8 9 4.6-1 8-4 8-9V6z"/><path d="m8.5 12 2.2 2.2 4.8-5"/></g></svg>`,
  db: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#2E6F9F" stroke-width="1.8" stroke-linecap="round"><ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v7c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 12v7c0 1.7 3.1 3 7 3s7-1.3 7-3v-7"/></g></svg>`,
  vector: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#6B4BB2" stroke-width="1.8" stroke-linecap="round"><circle cx="6" cy="16" r="2"/><circle cx="12" cy="7" r="2"/><circle cx="18" cy="13" r="2"/><path d="m7.5 14.5 3.2-5.7M13.7 8.2l2.8 3.3"/></g></svg>`,
  ai: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#6B4BB2" stroke-width="1.8" stroke-linecap="round"><circle cx="7" cy="7" r="2"/><circle cx="17" cy="7" r="2"/><circle cx="12" cy="17" r="2"/><path d="M9 7h6M8.2 8.5l2.8 6.7M15.8 8.5 13 15.2"/></g></svg>`,
  sort: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#2E6F9F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4v16M4 7l3-3 3 3M17 20V4M14 17l3 3 3-3"/></g></svg>`,
};
const svgUrl = svg => `data:image/svg+xml;base64,${Buffer.from(svg, "utf8").toString("base64")}`;

const presentation = Presentation.create({ slideSize: { width: W, height: H } });
const slide = presentation.slides.add();
slide.background.fill = C.white;

function rect(x, y, w, h, fill, line = "none", radius = 0, width = 0) {
  return slide.shapes.add({ geometry: "rect", position: { left: x, top: y, width: w, height: h }, fill,
    line: line === "none" ? { fill: "none", width: 0 } : { style: "solid", fill: line, width },
    ...(radius ? { borderRadius: radius } : {}) });
}
function textBox(text, x, y, w, h, size, color = C.ink, opts = {}) {
  const s = slide.shapes.add({ geometry: "textbox", position: { left: x, top: y, width: w, height: h }, fill: "none", line: { fill: "none", width: 0 } });
  s.text = text;
  s.text.style = { typeface: FONT, fontSize: size, color, bold: opts.bold ?? false, alignment: opts.align ?? "left",
    verticalAlignment: opts.valign ?? "top", autoFit: opts.autoFit ?? "shrinkText", wrap: "square",
    insets: opts.insets ?? { top: 0, right: 0, bottom: 0, left: 0 } };
  return s;
}
function icon(name, x, y, size = 26) {
  rect(x - 6, y - 6, size + 12, size + 12, C.white, "none", 9, 0);
  slide.images.add({ dataUrl: svgUrl(icons[name]), alt: `${name} pictogram`, fit: "contain", position: { left: x, top: y, width: size, height: size } });
}
function node({ x, y, w, h, fill, line, iconName, label, title, detail, lineWidth = 1.2 }) {
  rect(x, y, w, h, fill, line, 13, lineWidth);
  if (iconName) icon(iconName, x + 14, y + 18, 24);
  const tx = iconName ? x + 51 : x + 12;
  const tw = w - (iconName ? 63 : 24);
  textBox(label, tx, y + 11, tw, 13, 8.3, C.muted, { bold: true, valign: "middle" });
  textBox(title, tx, y + 29, tw, 25, 13.2, C.ink, { bold: true, valign: "middle" });
  textBox(detail, tx, y + 56, tw, h - 61, 9.3, C.muted, { valign: "top" });
}
function line(x, y, w, h, color = C.arrow, width = 1.7, arrow = false) {
  return slide.shapes.add({ geometry: "line", position: { left: x, top: y, width: w, height: h }, fill: "none",
    line: { style: "solid", fill: color, width }, ...(arrow ? { tail: { type: "triangle", width: "med", length: "med" } } : {}) });
}
function elbow(x1, y1, x2, y2, midX, color = C.arrow) {
  line(x1, y1, midX - x1, 0, color); line(midX, Math.min(y1, y2), 0, Math.abs(y2 - y1), color); line(midX, y2, x2 - midX, 0, color, 1.7, true);
}

textBox("CUSTOMER INTELLIGENCE", 52, 34, 1176, 20, 11.5, C.green, { bold: true });
textBox("정책 Hybrid RAG 검색과 근거 판정", 52, 61, 1176, 44, 32, C.ink, { bold: true, valign: "middle" });
textBox("권한 범위 안에서 후보를 찾고, 재정렬과 근거 판정을 거쳐 응답 상태를 결정합니다.", 52, 107, 1176, 24, 13.2, C.muted, { valign: "middle" });

const top = 158;
textBox("01  범위 제한", 48, top, 365, 24, 9.5, C.muted, { bold: true, valign: "middle" });
textBox("02  후보 검색과 정밀 재정렬", 448, top, 555, 24, 9.5, C.muted, { bold: true, valign: "middle" });
textBox("03  근거 판정과 응답", 1028, top, 204, 24, 9.5, C.muted, { bold: true, valign: "middle" });
line(48, top + 28, 365, 0, C.line, 1.4); line(448, top + 28, 555, 0, C.line, 1.4); line(1028, top + 28, 204, 0, C.line, 1.4);

node({ x: 48, y: 277, w: 150, h: 105, fill: C.grayBg, line: C.line, iconName: "question", label: "INPUT", title: "정책 질문", detail: "질문과 사용자 권한" });
node({ x: 228, y: 257, w: 190, h: 145, fill: "#F2FAF6", line: "#5E8B78", iconName: "shieldGreen", label: "SERVER FILTER", title: "정책 범위 필터", detail: "제품 범위·유효기간\nCollection·관할·부서" });
const filterBadge = rect(280, 363, 67, 18, C.white, C.green, 9, 0.8); filterBadge.text = "권한 강제"; filterBadge.text.style = { typeface: FONT, fontSize: 8, bold: true, color: C.green, alignment: "center", verticalAlignment: "middle", autoFit: "shrinkText", insets: { top:0,right:2,bottom:0,left:2 } };
node({ x: 458, y: 208, w: 190, h: 103, fill: C.blueBg, line: C.blue, iconName: "db", label: "KEYWORD", title: "PostgreSQL FTS", detail: "정확한 용어와 조건 검색" });
node({ x: 458, y: 364, w: 190, h: 103, fill: C.violetBg, line: C.violet, iconName: "vector", label: "SEMANTIC", title: "Embedding 기반 검색", detail: "질문과 Child 의미 유사도" });

const rrf = slide.shapes.add({ geometry: "ellipse", position: { left: 690, top: 273, width: 114, height: 114 }, fill: C.greenBg, line: { style: "solid", fill: C.green, width: 2 } });
rrf.text = "FUSION\nRRF\n두 검색 순위 통합\nk = 60";
rrf.text.style = { typeface: FONT, fontSize: 10, bold: true, color: C.green, alignment: "center", verticalAlignment: "middle", autoFit: "shrinkText", wrap: "square", insets: { top: 8, right: 8, bottom: 8, left: 8 } };

node({ x: 845, y: 241, w: 190, h: 177, fill: C.violetBg, line: C.violet, iconName: "ai", label: "RERANKER", title: "BGE-M3 재정렬", detail: "Multi-vector Late Interaction\n질문 토큰별 MaxSim", lineWidth: 2 });
const heat = [2,0,1,0,0, 0,2,0,1,0, 1,0,0,2,0];
for (let i = 0; i < heat.length; i++) {
  const row = Math.floor(i / 5), col = i % 5;
  rect(897 + col * 17, 370 + row * 12, 13, 8, heat[i] === 2 ? "#7551BD" : heat[i] === 1 ? "#AA92D8" : "#DFD5F4", "none", 2, 0);
}

node({ x: 1068, y: 213, w: 164, h: 84, fill: C.blueBg, line: C.blue, iconName: "sort", label: "POLICY RULE", title: "정책 우선순위", detail: "제품 범위·Authority·최신 버전" });
node({ x: 1068, y: 334, w: 164, h: 102, fill: "#F6F1FB", line: C.violet, iconName: "shieldViolet", label: "LLM JUDGMENT", title: "근거 유효성 판정", detail: "sufficient · insufficient · conflict", lineWidth: 2 });

const outcomes = [
  [668, C.greenBg, C.green, "SUFFICIENT", "근거 인용 답변", "유효 정책과 출처"],
  [812, C.grayBg, C.line, "INSUFFICIENT", "근거 부족", "no_evidence"],
  [956, C.amberBg, C.amber, "CONFLICT", "정책 충돌", "담당자 확인"],
  [1100, C.roseBg, C.rose, "MEDICAL · SAFETY", "즉시 Escalation", "안전 담당자 연결"],
];
for (const [x, fill, border, label, title, detail] of outcomes) {
  rect(x, 513, 132, 82, fill, border, 12, 1.2);
  textBox(label, x + 8, 524, 116, 12, 7.4, border === C.line ? C.muted : border, { bold: true, align: "center", valign: "middle" });
  textBox(title, x + 8, 543, 116, 21, 11.2, C.ink, { bold: true, align: "center", valign: "middle" });
  textBox(detail, x + 8, 568, 116, 16, 8.5, C.muted, { align: "center", valign: "middle" });
}

line(198, 329, 30, 0, C.arrow, 1.8, true);
elbow(418, 329, 458, 259, 438); elbow(418, 329, 458, 415, 438);
elbow(648, 259, 690, 330, 669); elbow(648, 415, 690, 330, 669);
line(804, 330, 41, 0, C.arrow, 1.8, true); line(1035, 330, 33, 0, C.arrow, 1.8, true); line(1150, 297, 0, 37, C.arrow, 1.8, true);
line(1150, 436, 0, 38, C.green, 1.8); line(734, 474, 416, 0, C.green, 1.8);
for (const x of [734, 878, 1022, 1166]) line(x, 474, 0, 39, C.green, 1.8, true);

line(48, 650, 1184, 0, C.line, 1);
textBox("핵심 통제:", 48, 663, 76, 20, 10.5, C.green, { bold: true, valign: "middle" });
textBox("검색 점수만으로 답변하지 않고, 사용자 권한과 근거 유효성 판정을 통과한 정책만 Agent 답변에 사용합니다.", 128, 663, 1104, 20, 10.5, "#46564F", { bold: true, valign: "middle" });

slide.speakerNotes.textFrame.setText(
  "구현 근거: src/rag/retriever.py, src/rag/rerankers.py, src/rag/evidence.py, src/rag/config.py. PostgreSQL FTS와 OpenAI Embedding 검색을 RRF로 통합하고, BGE-M3 multi-vector MaxSim 재정렬, 정책 우선순위, LLM 근거 유효성 판정을 거쳐 응답 상태를 결정한다."
);

const candidatePath = path.join(TMP_DIR, "policy_hybrid_rag_candidate.pptx");
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
const preview = await presentation.export({ slide, format: "png", scale: 1.4 });
await fs.writeFile(path.join(TMP_DIR, "policy_hybrid_rag_preview.png"), new Uint8Array(await preview.arrayBuffer()));
const layout = await slide.export({ format: "layout" });
await fs.writeFile(path.join(TMP_DIR, "policy_hybrid_rag_layout.json"), await layout.text());

const stagingDir = path.join(WORKSPACE_DIR, ".codex-finalizer");
await fs.mkdir(stagingDir, { recursive: true });
const staged = path.join(stagingDir, "policy_hybrid_rag_candidate.pptx");
await fs.copyFile(candidatePath, staged);
await finalizePresentation({
  explicitTotalSlideCount: 1,
  requiredNativeTableOwnerSlides: [],
  requiredNativeChartOwnerSlides: [],
  workspaceDir: WORKSPACE_DIR,
  candidatePath: staged,
  finalPath: FINAL_PPTX,
  pythonExecutable: RUNTIME_PYTHON,
  integrityValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_layout_geometry.py"),
  layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-bullet-geometry", "--validate-heading-fit"],
  fontPolicy: { basis: "design", families: [FONT], scriptFonts: { ea: FONT } },
  verifyArtifactToolImport: true,
  receiptPath: path.join(stagingDir, `${path.basename(FINAL_PPTX)}.validation.json`),
});

console.log(FINAL_PPTX);
