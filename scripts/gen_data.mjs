#!/usr/bin/env node
/**
 * gen_data.mjs —— 阶段 2：从 Remotion 工程采样出 AE 需要的 data.json
 *
 * 核心原则：不解析 JSX，直接 import Remotion 的纯函数模块，把结果采样成数组。
 * 前提：Remotion 工程的 src/ 下不依赖 React / remotion（见 references/remotion-authoring.md）。
 *
 * 用法：改下面 CONFIG 后 `node gen_data.mjs`
 * 自检：连跑两次，data.json 应字节级一致（md5 相同）。不一致说明用了 Math.random()。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

// ============ CONFIG：按你的工程改这里 ============
const SRC = 'C:/path/to/project/src';       // Remotion 工程的 src 目录
const OUT_DIR = path.dirname(fileURLToPath(import.meta.url));

const ENV_STEP = 0.5;    // 环境采样间隔（秒）
const CAM_STEP = 0.25;   // 相机采样间隔
const TRAIL_STEP = 0.08; // 快速运动物体采样间隔

// 模块名 → 你的工程里实际的文件
const MODS = {
  cues: 'cues.js',        // 导出 LYRICS / DURATION
  director: 'director.js',// 导出 camAt(t) / buildTracks()
  rng: 'rng.js',          // 导出 clamp / lerp / hash1 / hash2
};
// =================================================

const imp = (rel) => import(pathToFileURL(path.join(SRC, rel)).href);
const { LYRICS, DURATION } = await imp(MODS.cues);
const { camAt, buildTracks } = await imp(MODS.director);
const { clamp } = await imp(MODS.rng);

const tracks = buildTracks();
const fps = 30;
const r2 = (v) => Math.round(v * 100) / 100;

// ---- 环境：每条轨道按 ENV_STEP 采样 ----
// 左边是 AE 侧 ENV 控制器上的滑块名，右边是 Remotion buildTracks() 里返回的函数名。
// 改这里要同步改 gen_build.mjs 里的 ENV 滑块，否则 AE 里会多/少一个滑块。
const ENV_TRACKS = {
  Season: 'season',
  Daylight: 'daylight',
  Sunset: 'sunset',
  Wind: 'wind',
  LeafAmt: 'leafAmt',
};
const ENV_KEYS = Object.keys(ENV_TRACKS);

// 缺轨道直接抛错，不要静默填 0。
// 静默降级的后果是：AE 里那条曲线从头到尾是平的，排查时根本想不到是数据层的问题。
for (const [slider, fnName] of Object.entries(ENV_TRACKS)) {
  if (typeof tracks[fnName] !== 'function') {
    throw new Error(
      `buildTracks() 没有导出 "${fnName}"（ENV 滑块 "${slider}" 需要它）。` +
      `检查 director.js，或在 ENV_TRACKS 里改正映射。`
    );
  }
}

const env = [];
for (let t = 0; t <= DURATION + 1e-6; t += ENV_STEP) {
  const row = [r2(t)];
  for (const k of ENV_KEYS) {
    row.push(r2(tracks[ENV_TRACKS[k]](t)[0]));
  }
  env.push(row);
}

// ---- 相机：Position 关键帧 ----
const cam = [];
for (let t = 0; t <= DURATION + 1e-6; t += CAM_STEP) {
  const c = camAt(t);
  cam.push([r2(t), Math.round(c.x * 10) / 10, Math.round(c.y * 10) / 10, r2(c.zoom ?? 1)]);
}

// ---- 轨迹：主运动物体（可选，按你的片子加）----
// 用固定种子重算，不要 Math.random()
const trail = [];
// for (let t = t0; t <= t1; t += TRAIL_STEP) { const s = objAt(t); trail.push([r2(t), s.x, s.y, r2(s.rot)]); }

// ---- 时间轴 ----
const lyrics = LYRICS.map((l) => ({ t: r2(l.t), end: r2(l.end ?? l.t + (l.dur ?? 3)), text: l.text }));

// ---- 输出 ----
const data = {
  dur: DURATION,
  fps,
  envKeys: ENV_KEYS,
  env,
  cam,
  trail,
  lyrics,
  // sec / flashes / memory / anchors …按需要补
};

fs.writeFileSync(path.join(OUT_DIR, 'data.json'), JSON.stringify(data));
console.log(
  'data.json written:',
  'dur', DURATION,
  '| env', env.length,
  '| cam', cam.length,
  '| lyrics', lyrics.length,
);
