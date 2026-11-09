# Remotion 工程规范

这套工程规范的目的不只是"能渲染"，而是**能被 `gen_data.mjs` 反向 import 出数值**。
写法一旦跑偏，后面转 AE 就无解。

## 目录与职责

```
proj/
├── src/                     ← 全部纯逻辑，禁止 import React / remotion
│   ├── cues.js              [{ t, end, text }] 歌词/字幕时间轴
│   ├── segments.js          [{ name, t, end }] 段落
│   ├── palette.js          颜色常量（唯一配色真源）
│   ├── rng.js               mulberry32 / hash1 / hash2 / clamp / lerp / easings
│   ├── director.js          轨道函数：season(t) / daylight(t) / sunset(t) / wind(t) / camAt(t)
│   └── world/               场景元素，每个模块导出纯函数或确定性构建器
├── remotion/
│   ├── entry.jsx            Composition，durationInFrames = round(dur*fps)
│   └── Frame.jsx            第 n 帧 = f(n)，只做渲染，不做计算
└── public/                  图片、字体、3D 帧序列、AI 素材
```

**硬约束**：`src/` 下任何文件都不许 `import React` 或 `import { useCurrentFrame }`。
一旦引入，`gen_data.mjs` 就无法在 Node 里跑它。

## 纯函数化：Remotion 侧怎么写才可复用

```js
// ✅ 正确：给 t 返回状态，无副作用，可被 Node import
export const camAt = (t) => ({ x: 960 + Math.sin(t * 0.3) * 40, y: 470, zoom: 1 + t * 0.002 });
export const buildTracks = () => ({
  season:   (t) => [seasonValue(t)],
  daylight: (t) => [daylightValue(t)],
});

// ❌ 错误：依赖 React 生命周期 / 全局可变状态 / Math.random()
export const useCam = () => { const f = useCurrentFrame(); ... };
let seed = Math.random();
```

组件层只负责"把纯函数的结果画出来"：

```jsx
const Frame = () => {
  const frame = useCurrentFrame();
  const t = frame / fps;
  const c = camAt(t);                  // 纯函数调用
  return <div style={{ transform: `translate(${c.x}px, ${c.y}px)` }} />;
};
```

## 随机性：必须固定种子

```js
import { mulberry32 } from './rng.js';
const rnd = mulberry32(20261024);     // 固定种子
```

- 禁止 `Math.random()`
- 禁止 `Date.now()` 参与任何影响画面的计算
- 生成结构（树、粒子分布、照片分配）时，把 `rnd()` 的**调用顺序**当成契约：
  改了顺序 = 换了整棵树 = AE 侧几何全对不上

自检：同一工程渲两次，同帧截图 md5 应一致。

## 数据文件设计

**cues 的 `dur` 是"这句唱多久"，不是"到下一句的间隔"。**

```js
// ✅
{ t: 89.94, dur: 3.9, text: "你不见不再身边" }   // 唱完就结束，后面的间奏单独处理

// ❌ 会导致整段死帧
{ t: 89.94, dur: 21.76, text: "你不见不再身边" } // 把 21.8 秒间奏算成了这句的时长
```

间奏要用**独立的分镜序列**填（每镜 2.4–3.6 s），不要靠拉长一句歌词的时长。

## 帧渲染的三个结构性坑

### 1. `TransitionSeries` 吃时长

`TransitionSeries` 的总长 = Σ各段 − Σ转场。139 个转场 × 22 帧会吃掉 100+ 秒。
必须做代数补偿：

```
A_0 = 0
A_i = A_{i-1} + S_{i-1} − T_i
令 A_i = b_i − ⌊T_i/2⌋
⇒ S_i = A_{i+1} − A_i + T_{i+1}
⇒ S_{N-1} = D − A_{N-1}
∴ ΣS = D + ΣT  ⇒  总长 = D
```

并在代码里断言：

```js
if (plan.total !== total) throw new Error(`转场补偿失败：${plan.total} ≠ ${total}`);
```

宁可渲染失败，不要出错位的片子。

### 2. 颗粒/噪点层按秒换 = 死帧

```jsx
// ❌ 同一秒内 30 帧颗粒完全相同 → 像素级重复帧
const i = Math.floor(frame / 30) % 3;

// ✅ 逐帧换 + 位移抖动
const i = frame % 3;
const jx = (frame * 7) % 64, jy = (frame * 11) % 64;
// backgroundPosition: `${jx}px ${jy}px`
```

底图静止时这个 bug 会直接产生 `帧差 = 0` 的连续帧，量化审核会抓出来。

### 3. 文字基准与图片基准撞在同一高度

文字 `top: 52%`、照片容器 `top: 52%` → 文字必然压住照片下缘。
给两者留 **≥48 px** 硬间距，并在代码里断言：

```js
const gap = textTop - photoBottom;
if (gap < 48) { /* 把文字继续下推 */ }
```

## 素材规范

**入片前必须过三道筛**（脚本化，别靠肉眼）：

1. **可辨文字**：商业招牌、清晰书封、门牌、价签、水印 → 排除。
   画面里出现可读文字等于在 MV 里插广告。
2. **高饱和**：整图 HSV 的 S 均值 > 0.32，或存在面积 > 2% 的 S > 0.6 色块 → 排除。
   一个大红招牌能毁掉全片的低饱和基调。
3. **人物**：中远景人群、明显人脸 → 排除（除剧情需要）。

同时限制**同类构图占比**。"书脊排列"这类构图如果超过全片 35%，视觉会高度同质化。

## AI 生图素材的落地流程

```
生成 → 去平台水印 → 精确尺寸校准 → 登记清单 → 引用
```

1. **水印**：生图工具常在右下角硬嵌平台水印（`AI生成 / xxx`），`footnote` 参数关不掉。
   入片前必须本地去除，否则穿帮。做法见 `scripts/prepare_ai.py`。
2. **尺寸**：模型常输出 1920×1072 这类"接近但不是"的尺寸。
   用 `ImageOps.fit(im, (1920,1080), LANCZOS)` 居中裁到精确值，不要留 8 px 黑边。
3. **透明素材**：`background:"transparent"` 可能不生效（返回 RGB）。
   用 `scripts/cutout_bg.py` 按 HSV 的 V/S 双判据抠，不要用"与背景色差"。
4. **登记**：维护一个 `ai.json` 清单（`{items:["AI-01",...]}`），代码里 `hasAi(id)` 判断有则用。
   缺图时自动跳过，保证"没有 AI 素材也能渲染成立"。

## 调试节奏（省时间的核心）

| 要看的 | 做法 | 耗时 |
|---|---|---|
| 一句歌词的排版 | `--frames=620-650`（30 帧） | ~40 s |
| 一个转场 | `--frames=95-110`（16 帧） | ~25 s |
| 单帧构图 | `remotion still ... --frame=400` | 2–4 s |
| 整段 30 秒 | 只在确认后跑一次 | 15 min（2 核机器） |

**一版最多渲 3 个 1 秒片段**，都对再进整段。
