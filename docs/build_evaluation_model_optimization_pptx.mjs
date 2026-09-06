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
const W = 1280, H = 720;
const C = { white:"#FFFFFF", ink:"#17231F", muted:"#64716B", line:"#D8E3DE", arrow:"#8B9992", green:"#27664F", greenBg:"#EDF7F2", blue:"#2E6F9F", blueBg:"#EDF6FC", violet:"#6B4BB2", violetBg:"#F1ECFB", amber:"#A56216", amberBg:"#FFF5E6", grayBg:"#F7F9F8" };
const icons = {
  set:`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#68756F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4h10v3H7zM5 6h14v15H5z"/><path d="m8 12 2 2 4-4M8 18h8"/></g></svg>`,
  modelBlue:`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#2E6F9F" stroke-width="1.8" stroke-linecap="round"><circle cx="7" cy="7" r="2"/><circle cx="17" cy="7" r="2"/><circle cx="12" cy="17" r="2"/><path d="M9 7h6M8.2 8.5l2.8 6.7M15.8 8.5 13 15.2"/></g></svg>`,
  modelGreen:`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#27664F" stroke-width="1.8" stroke-linecap="round"><circle cx="7" cy="7" r="2"/><circle cx="17" cy="7" r="2"/><circle cx="12" cy="17" r="2"/><path d="M9 7h6M8.2 8.5l2.8 6.7M15.8 8.5 13 15.2"/></g></svg>`,
  modelViolet:`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#6B4BB2" stroke-width="1.8" stroke-linecap="round"><circle cx="7" cy="7" r="2"/><circle cx="17" cy="7" r="2"/><circle cx="12" cy="17" r="2"/><path d="M9 7h6M8.2 8.5l2.8 6.7M15.8 8.5 13 15.2"/></g></svg>`,
  trace:`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#27664F" stroke-width="1.8" stroke-linecap="round"><path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5"/></g></svg>`,
  check:`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#2E6F9F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4 6v6c0 5 3.4 8 8 9 4.6-1 8-4 8-9V6z"/><path d="m8.5 12 2.2 2.2 4.8-5"/></g></svg>`,
  search:`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#27664F" stroke-width="1.8" stroke-linecap="round"><circle cx="10" cy="10" r="6"/><path d="m14.5 14.5 5 5M7 10h6"/></g></svg>`,
  judge:`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="#6B4BB2" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v16M6 7h12M7 7l-3 6h6zM17 7l-3 6h6zM8 20h8"/></g></svg>`,
};
const svgUrl = svg => `data:image/svg+xml;base64,${Buffer.from(svg,"utf8").toString("base64")}`;
const presentation = Presentation.create({ slideSize:{ width:W,height:H } });
const slide = presentation.slides.add(); slide.background.fill = C.white;

function rect(x,y,w,h,fill,lineColor="none",radius=0,width=0,dashed=false){return slide.shapes.add({geometry:"rect",position:{left:x,top:y,width:w,height:h},fill,line:lineColor==="none"?{fill:"none",width:0}:{style:dashed?"dash":"solid",fill:lineColor,width},...(radius?{borderRadius:radius}:{})});}
function textBox(text,x,y,w,h,size,color=C.ink,opts={}){const s=slide.shapes.add({geometry:"textbox",position:{left:x,top:y,width:w,height:h},fill:"none",line:{fill:"none",width:0}});s.text=text;s.text.style={typeface:FONT,fontSize:size,color,bold:opts.bold??false,alignment:opts.align??"left",verticalAlignment:opts.valign??"top",autoFit:opts.autoFit??"shrinkText",wrap:"square",insets:opts.insets??{top:0,right:0,bottom:0,left:0}};return s;}
function icon(name,x,y,size=25){rect(x-6,y-6,size+12,size+12,C.white,"none",9,0);slide.images.add({dataUrl:svgUrl(icons[name]),alt:`${name} pictogram`,fit:"contain",position:{left:x,top:y,width:size,height:size}});}
function line(x,y,w,h,color=C.arrow,width=1.7,arrow=false,dashed=false){return slide.shapes.add({geometry:"line",position:{left:x,top:y,width:w,height:h},fill:"none",line:{style:dashed?"dash":"solid",fill:color,width},...(arrow?{tail:{type:"triangle",width:"med",length:"med"}}:{})});}
function card({x,y,w,h,fill,border,label,title,detail,iconName,lineWidth=1.2,dashed=false}){rect(x,y,w,h,fill,border,13,lineWidth,dashed);if(iconName)icon(iconName,x+15,y+18,24);const tx=iconName?x+52:x+13,tw=w-(iconName?65:26);textBox(label,tx,y+11,tw,13,8.2,C.muted,{bold:true,valign:"middle"});textBox(title,tx,y+29,tw,31,12.8,C.ink,{bold:true,valign:"middle"});textBox(detail,tx,y+62,tw,h-67,9.2,C.muted,{valign:"top"});}
function badge(text,x,y,w,color){const b=rect(x,y,w,18,C.white,color,9,.8);b.text=text;b.text.style={typeface:FONT,fontSize:7.8,bold:true,color,alignment:"center",verticalAlignment:"middle",autoFit:"shrinkText",wrap:"none",insets:{top:0,right:2,bottom:0,left:2}};}
function modelCard({x,fill,border,step,title,detail,iconName,badgeText,dashed=false,emphasis=false}){rect(x,300,126,155,fill,border,13,emphasis?2.4:1.2,dashed);textBox(step,x+13,311,72,13,8.2,C.muted,{bold:true,valign:"middle"});icon(iconName,x+92,311,19);textBox(title,x+13,341,100,24,12.4,C.ink,{bold:true,valign:"middle",autoFit:"shrinkText"});textBox(detail,x+13,373,100,36,9.1,C.muted,{valign:"top"});badge(badgeText,x+13,421,100,border);}
function evalCard({y,fill,border,label,title,detail,iconName}){rect(868,y,210,72,fill,border,13,1.2);icon(iconName,881,y+20,22);textBox(label,917,y+10,148,12,8,C.muted,{bold:true,valign:"middle"});textBox(title,917,y+27,148,21,12.2,C.ink,{bold:true,valign:"middle"});textBox(detail,917,y+51,148,14,8.3,C.muted,{valign:"middle"});}

textBox("CUSTOMER INTELLIGENCE",52,34,1176,20,11.5,C.green,{bold:true});
textBox("평가 자동화와 모델 최적화",52,61,1176,44,32,C.ink,{bold:true,valign:"middle"});
textBox("고성능 모델로 설계를 검증한 뒤, 같은 평가 기준으로 운영 모델과 로컬 후보를 비교합니다.",52,107,1176,24,13.2,C.muted,{valign:"middle"});
const py=165;
for(const [x,w,t] of [[48,152,"01  평가 입력"],[228,420,"02  모델 전환 과정"],[678,160,"03  결과 수집"],[868,210,"04  공통 평가 체계"],[1108,124,"05  비교"]]){textBox(t,x,py,w,24,9.4,C.muted,{bold:true,valign:"middle"});line(x,py+28,w,0,C.line,1.4);}

card({x:48,y:273,w:152,h:205,fill:C.grayBg,border:C.line,label:"FIXED EVAL SET",title:"같은 질문과\n기대 결과",detail:"모델이 바뀌어도\n동일한 기준으로 비교",iconName:"set"});
badge("리뷰 분석",60,438,44,C.blue);badge("정책 RAG",108,438,52,C.green);badge("안전",164,438,30,C.amber);
line(228,250,420,0,C.line,1);line(228,495,420,0,C.line,1);
modelCard({x:228,fill:C.blueBg,border:C.blue,step:"STEP 1",title:"Sol 검증",detail:"설계 타당성\n품질 상한 확인",iconName:"modelBlue",badgeText:"초기 Reference"});
modelCard({x:375,fill:C.greenBg,border:C.green,step:"STEP 2",title:"Luna·Terra",detail:"Luna: 추출·근거\nTerra: 최종 Agent",iconName:"modelGreen",badgeText:"API 운영 기준",emphasis:true});
modelCard({x:522,fill:C.violetBg,border:C.violet,step:"STEP 3",title:"Qwen·Gemma",detail:"로컬 전환 후보\n향후 GPU 검증",iconName:"modelViolet",badgeText:"검토 중",dashed:true});
line(354,377,21,0,C.arrow,1.7,true);line(501,377,21,0,C.arrow,1.7,true);

card({x:678,y:303,w:160,h:175,fill:"#F8FBFA",border:C.line,label:"EXECUTION TRACE",title:"실행 결과 수집",detail:"",iconName:"trace"});
for(const [x,y,t] of [[692,390,"Tool Call"],[758,390,"SQL 수치"],[692,424,"RAG 근거"],[758,424,"최종 답변"]]){const b=rect(x,y,58,25,C.white,C.line,7,.7);b.text=t;b.text.style={typeface:FONT,fontSize:7.7,bold:true,color:C.muted,alignment:"center",verticalAlignment:"middle",autoFit:"shrinkText",insets:{top:0,right:1,bottom:0,left:1}};}

evalCard({y:237,fill:C.blueBg,border:C.blue,label:"DETERMINISTIC",title:"Tool·Rule 평가",detail:"선택·인자·수치·금지 규칙",iconName:"check"});
evalCard({y:324,fill:C.greenBg,border:C.green,label:"STAGE COMPARISON",title:"RAG 단계 평가",detail:"검색·재정렬·근거 판정",iconName:"search"});
evalCard({y:411,fill:C.violetBg,border:C.violet,label:"LLM JUDGE",title:"Sol 정성 평가",detail:"근거성·분석·업무 활용성",iconName:"judge"});

rect(1108,267,124,206,C.white,C.green,13,2);textBox("SCORECARD",1121,279,98,13,8.2,C.muted,{bold:true});textBox("비교 결과표",1121,298,98,27,12.8,C.ink,{bold:true,valign:"middle"});
for(const [y,t,color] of [[337,"통과 항목",C.green],[372,"실패 위치",C.amber],[407,"품질 차이",C.violet]]){rect(1121,y,98,27,C.grayBg,"none",7,0);slide.shapes.add({geometry:"ellipse",position:{left:1129,top:y+10,width:7,height:7},fill:color,line:{fill:"none",width:0}});textBox(t,1141,y+5,70,17,8.7,C.ink,{bold:true,valign:"middle"});}
textBox("총점보다 실패 원인과\n모델 간 차이를 기록",1121,443,98,22,7.8,C.muted,{valign:"middle"});

line(200,375,28,0,C.arrow,1.7,true);line(648,375,30,0,C.arrow,1.7,true);
line(838,390,15,0,C.arrow,1.7);line(853,273,0,174,C.arrow,1.7);for(const y of [273,360,447])line(853,y,15,0,C.arrow,1.7,true);
for(const y of [273,360,447])line(1078,y,15,0,C.arrow,1.7);line(1093,273,0,174,C.arrow,1.7);line(1093,360,15,0,C.arrow,1.7,true);

rect(348,540,884,45,C.amberBg,C.amber,13,1.2,true);textBox("평가 결과 기반 개선",365,552,134,20,10.3,C.amber,{bold:true,valign:"middle"});textBox("Prompt · 역할별 모델 · 검색 설정 · 평가 케이스 보완",509,552,425,20,9.7,"#765023",{bold:true,valign:"middle"});textBox("운영 기준으로 재평가 ↩",1024,552,190,20,9.4,"#765023",{bold:true,align:"right",valign:"middle"});
line(1170,473,0,67,C.amber,1.4,true,true);line(438,455,0,85,C.amber,1.4,false,true);

line(48,650,1184,0,C.line,1);textBox("핵심:",48,663,45,20,10.5,C.green,{bold:true,valign:"middle"});textBox("Sol은 초기 설계 검증에 사용하고, Luna·Terra를 API 운영 기준으로 최적화한 뒤 Qwen·Gemma의 로컬 전환 가능성을 같은 평가 체계로 확인합니다.",98,663,1134,20,10.2,"#46564F",{bold:true,valign:"middle"});

slide.speakerNotes.textFrame.setText("프로젝트 평가 구조: 고정 평가 세트, Tool·Rule 검사, RAG 단계 비교, Sol LLM Judge를 결합한다. Sol은 초기 타당성 검증과 품질 상한 확인에 사용하고, Luna·Terra 구성을 API 운영 기준으로 최적화하며, Qwen·Gemma 로컬 후보는 향후 GPU 환경에서 같은 평가 기준으로 검증한다.");
const candidate=path.join(TMP_DIR,"evaluation_model_optimization_candidate.pptx");await(await PresentationFile.exportPptx(presentation)).save(candidate);const preview=await presentation.export({slide,format:"png",scale:1.4});await fs.writeFile(path.join(TMP_DIR,"evaluation_model_optimization_preview.png"),new Uint8Array(await preview.arrayBuffer()));const layout=await slide.export({format:"layout"});await fs.writeFile(path.join(TMP_DIR,"evaluation_model_optimization_layout.json"),await layout.text());
const staging=path.join(WORKSPACE_DIR,".codex-finalizer");await fs.mkdir(staging,{recursive:true});const staged=path.join(staging,"evaluation_model_optimization_candidate.pptx");await fs.copyFile(candidate,staged);
await finalizePresentation({explicitTotalSlideCount:1,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],workspaceDir:WORKSPACE_DIR,candidatePath:staged,finalPath:FINAL_PPTX,pythonExecutable:RUNTIME_PYTHON,integrityValidatorPath:path.join(SKILL_DIR,"container_tools/inspect_presentation_package_integrity.py"),layoutValidatorPath:path.join(SKILL_DIR,"container_tools/inspect_presentation_layout_geometry.py"),layoutArgs:["--expected-slide-size-emu","12192000,6858000","--validate-bullet-geometry","--validate-heading-fit"],fontPolicy:{basis:"design",families:[FONT],scriptFonts:{ea:FONT}},verifyArtifactToolImport:true,receiptPath:path.join(staging,`${path.basename(FINAL_PPTX)}.validation.json`)});
console.log(FINAL_PPTX);
