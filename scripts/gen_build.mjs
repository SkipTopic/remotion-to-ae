#!/usr/bin/env node
/**
 * gen_build.mjs —— 阶段 3 骨架：data.json → AE ExtendScript（可编辑工程构建器）
 *
 * 输出的 .jsx 在 AE 里执行（File > Scripts > Run Script File...）。
 * 生成的是原生形状层 / 文本层 / 关键帧 / 表达式，不是视频贴片。
 *
 * 用法：node gen_build.mjs  → 产出 build.jsx
 * 注意：生成的脚本开头会清空当前 AE 工程，执行前必须存盘。
 *
 * 详细规范见 references/ae-build-cookbook.md
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));

// ============ CONFIG ============
const COMP_NAME = 'MAIN';
const WIDTH = 1920;
const HEIGHT = 1080;
const OUT_AEP = 'C:/path/to/out/project_AE.aep';
const FONT_PS = 'ZCOOLXiaoWei-Regular'; // PostScript 名，不是家族名
// ================================

const DATA = JSON.parse(fs.readFileSync(path.join(HERE, 'data.json'), 'utf8'));

// ---- 工具：颜色一律 0-1 三元数组 ----
const hex2rgb = (h) => {
  const n = parseInt(h.slice(1), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]
    .map((v) => +v.toFixed(4));
};

// ---- 工具：采样数组 → [[t, v], ...] ----
const keysFrom = (rows, col, scale = 1) => rows.map((r) => [r[0], +(r[col] * scale).toFixed(3)]);

// ================= body：逐块构建图层 =================
function buildBody(D) {
  let s = '';

  // --- ENV / CAM 两个引导层 ---
  s += `
// ===== ENV / CAM 控制层（guideLayer 不参与渲染，但表达式能读）=====
var envL = comp.layers.addNull(); envL.name = "ENV"; envL.guideLayer = true;
var camL = comp.layers.addNull(); camL.name = "CAM"; camL.guideLayer = true;
`;
  (D.envKeys || []).forEach((k, i) => {
    s += `addSlider(envL, ${JSON.stringify(k)}, ${JSON.stringify(keysFrom(D.env, i + 1))});\n`;
  });
  if (D.cam && D.cam.length) {
    s += `addSlider(camL, "ZOOM", ${JSON.stringify(D.cam.map((c) => [c[0], c[3]]))});\n`;
    s += `setKeys(camL.transform.position, ${JSON.stringify(D.cam.map((c) => [c[0], [c[1], c[2]]]))});\n`;
  }

  // --- 背景层：由 ENV 滑块驱动，不写死颜色 ---
  s += `
// ===== 背景（ENV.Daylight 驱动亮度）=====
var bg = shLayer("BG");
grp(bg, "rect", [[-300,-300],[2220,-300],[2220,1380],[-300,1380]], true,
    [${hex2rgb('#EFE7D6').map((v) => v.toFixed(4)).join(',')}], 100);
opExpr(bg, "return 70 + E('Daylight')*30;");
`;

  // --- 轨迹物体：位置关键帧来自 data.trail ---
  if (D.trail && D.trail.length) {
    s += `
// ===== 轨迹物体（位置关键帧来自 data.trail）=====
var objL = shLayer("Obj");
ell(objL, "dot", [0,0], [40,40], [${hex2rgb('#B3542E').map((v) => v.toFixed(4)).join(',')}], 100);
setKeys(objL.transform.position, ${JSON.stringify(D.trail.map((r) => [r[0], [r[1], r[2]]]))});
`;
  }

  // --- 文本层示例（记得换 postScriptName）---
  s += `
// ===== 文本层示例 =====
var txt = comp.layers.addText("示例文字");
try {
  var td = txt.property("Source Text").value;
  td.font = FONTPS; td.fontSize = 72; td.applyFill = true;
  td.fillColor = [${hex2rgb('#1A1712').map((v) => v.toFixed(4)).join(',')}];
  txt.property("Source Text").setValue(td);
} catch(e){ say("text fail: " + e); }
txt.transform.position.setValue([960, 540]);
`;

  // --- 时间轴标记：AE 里跳段落用 ---
  if (D.sections && D.sections.length) {
    s += `
// ===== 时间轴标记 =====
var marks = ${JSON.stringify(D.sections)};
for (var mi = 0; mi < marks.length; mi++) {
  try { comp.markerProperty.setValueAtTime(marks[mi].t, new MarkerValue(marks[mi].name)); } catch(e){}
}
`;
  }

  return s;
}

// ================= 组装完整 JSX =================
const jsx = `
// 由 gen_build.mjs 生成 · ${new Date().toISOString()}
// 执行前请存盘：本脚本会清空当前工程

var DATA = ${JSON.stringify(DATA)};
var FONTPS = ${JSON.stringify(FONT_PS)};
var OUTAEP = ${JSON.stringify(OUT_AEP)};
var LOG = [];
function say(s){ LOG.push(s); }
function flushLog(){
  try {
    var f = new File(OUTAEP.replace(/\\.aep$/i, '_buildlog.txt'));
    f.encoding = "UTF-8"; f.open("w");
    f.write(LOG.join("\\n")); f.close();
  } catch(e){}
}

// ---- 清空工程（危险）----
while (app.project.numItems > 0) { try { app.project.item(1).remove(); } catch(e){ break; } }

var comp = app.project.items.addComp(${JSON.stringify(COMP_NAME)}, ${WIDTH}, ${HEIGHT}, 1, DATA.dur, DATA.fps);

// ================= 工具函数 =================
function shLayer(name){ var l = comp.layers.addShape(); l.name = name; return l; }

function grp(l, name, pts, closed, color, op, sw, scol){
  var g = l.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
  try { g.name = name; } catch(e){}
  var c = g.property("Contents");
  var sh = c.addProperty("ADBE Vector Shape - Group");
  var sp = new Shape(); sp.vertices = pts; sp.closed = !!closed;
  sh.property("ADBE Vector Shape").setValue(sp);
  if (color) {
    var f = c.addProperty("ADBE Vector Graphic - Fill");
    f.property("ADBE Vector Fill Color").setValue(color);
    if (op != null) f.property("ADBE Vector Fill Opacity").setValue(op);
  }
  if (sw) {
    var st = c.addProperty("ADBE Vector Graphic - Stroke");
    st.property("ADBE Vector Stroke Color").setValue(scol || [0,0,0]);
    st.property("ADBE Vector Stroke Width").setValue(sw);
  }
  return g;
}

function ell(l, name, ctr, size, color, op){
  var g = l.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
  try { g.name = name; } catch(e){}
  var c = g.property("Contents");
  var el = c.addProperty("ADBE Vector Shape - Ellipse");
  el.property("Size").setValue(size);
  el.property("Position").setValue(ctr);
  var f = c.addProperty("ADBE Vector Graphic - Fill");
  f.property("ADBE Vector Fill Color").setValue(color);
  if (op != null) f.property("ADBE Vector Fill Opacity").setValue(op);
  return g;
}

function addFeatherMask(l, pts, feather){
  try {
    var grpM = null;
    try { grpM = l.property("ADBE Mask Parade"); } catch(eA){}   // 形状层
    if (!grpM) { grpM = l.property("ADBE Masks"); }              // 素材层
    var mk = grpM.addProperty("ADBE Mask Atom");
    var msp = new Shape(); msp.vertices = pts; msp.closed = true;
    mk.property("ADBE Mask Shape").setValue(msp);
    try { mk.property("ADBE Mask Feather").setValue([feather, feather]); } catch(eF){}
  } catch(e){ say("mask fail: " + e); }
}

var KEYERR = [];
function setKeys(prop, keys){
  var mn = "?";
  try { mn = prop.matchName; } catch(e0){}
  for (var i = 0; i < keys.length; i++) {
    try { prop.setValueAtTime(keys[i][0], keys[i][1]); }
    catch(e2){ KEYERR.push(mn + "@" + keys[i][0]); }
  }
}

function addSlider(layer, name, keys){
  var fx = layer.property("ADBE Effect Parade").addProperty("ADBE Slider Control");
  try { fx.name = name; } catch(e){}
  var p = fx.property("ADBE Slider Control-0001");
  if (keys && keys.length) setKeys(p, keys); else p.setValue(0);
  return fx;
}

// ---- 表达式前奏：只做"读控制器 + 一行映射" ----
var PRELUDE =
  "function E(s){return thisComp.layer('ENV').effect(s)('ADBE Slider Control-0001');}\\n" +
  "function CAM(){var c=thisComp.layer('CAM').transform.position;return [c[0],c[1]];}\\n" +
  "function ZM(){return thisComp.layer('CAM').effect('ZOOM')('ADBE Slider Control-0001');}\\n" +
  "function camP(ax,ay,d){var c=CAM();var z=1+(ZM()-1)*d;return [960+(ax-(960+(c[0]-960)*d))*z,540+(ay-(540+(c[1]-540)*d))*z];}\\n" +
  "function camS(d){return (1+(ZM()-1)*d)*100;}\\n" +
  "function LP(a,b,k){return a+(b-a)*k;}\\n" +
  "function MC(a,b,k){return [LP(a[0],b[0],k),LP(a[1],b[1],k),LP(a[2],b[2],k)];}\\n";

function ex(code){ return PRELUDE + code; }
function opExpr(l, code){ l.transform.opacity.expression = ex(code); }
function posExpr(l, code){ l.transform.position.expression = ex(code); }
function rotExpr(l, code){ l.transform.rotation.expression = ex(code); }
function opKeys(l, keys){ setKeys(l.transform.opacity, keys); }

function anchorLayer(l, ax, ay, d){
  l.transform.anchorPoint.setValue([ax, ay]);
  l.position.expression = ex("return camP(" + ax + "," + ay + "," + d + ");");
  l.scale.expression = ex("return [camS(" + d + "),camS(" + d + ")];");
}

${buildBody(DATA)}

// ================= 收尾 =================
say("图层总数 " + comp.numLayers);
say("KEYERR " + KEYERR.length + " 条: " + KEYERR.slice(0, 20).join(", "));
try { app.project.save(new File(OUTAEP)); say("已保存 " + OUTAEP); }
catch(e){ say("保存失败: " + e); }
flushLog();
__AE_BUILD_RESULT = { ok: true, layers: comp.numLayers, keyErr: KEYERR.slice(0, 10), log: LOG.slice(-30) };
`;

fs.writeFileSync(path.join(HERE, 'build.jsx'), jsx, 'utf-8');
console.log('build.jsx written,', Math.round(jsx.length / 1024), 'KB');
