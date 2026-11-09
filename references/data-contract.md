# data.json 契约

`gen_data.mjs` 的输出，是 Remotion 与 AE 之间**唯一的数据接口**。
一个 JSON 文件装下 AE 侧需要的全部数值，AE 脚本不再访问 Remotion 工程。

## 为什么是"采样成数组"而不是"AE 里现算"

AE 表达式引擎做**逐帧求值**，能力强但性能差：一个表达式在 218 层 × 7893 帧上
重复求值会直接把预览拖死。所以：

- 复杂计算（颜色混合、季节权重、缓动曲线）→ **Node 侧算好，转成关键帧数组**
- AE 侧只保留"读控制器 + 一行映射"，例如 `return E('Sunset')*13;`

判断标准：如果一个值在时间轴上变化平滑且需要多步运算，就提前算；
如果它只是"读某滑块 × 常数"，就留给表达式。

## 字段契约

```jsonc
{
  "dur": 263.109,          // 秒。唯一时长真源
  "fps": 30,

  // ---- 时间轴 ----
  "lyrics": [              // 逐句歌词/字幕，用于层出现时机与时间轴标记
    { "t": 12.26, "end": 16.52, "text": "秋阳沉默的午后", "key": false }
  ],
  "sec": {                 // 段落结构，AE 时间轴标记直接用
    "INTRO": { "start": 0, "end": 12.26 },
    "V1":    { "start": 12.26, "end": 45.54 }
  },

  // ---- 环境（0.5 s 采样）----
  // [t, season, daylight, sunset, wind]
  // season:  0=秋 1=冬 2=春 3=夏（可小数，表示过渡权重）
  // daylight:0=夜 0.5=正午 1=夜（白昼曲线，两端都是夜）
  // sunset:  0..1 晚霞强度
  // wind:    0..1 风力
  "env": [[0, 0, 0.32, 0.8, 0.2], [0.5, 0.002, 0.33, 0.79, 0.21]],

  // ---- 相机（0.25 s 采样）----
  // [t, x, y, zoom]  AE 侧转 Position / Scale 关键帧，场景层用表达式读它做视差
  "cam": [[0, 960, 470, 1.0]],

  // ---- 轨迹（0.08–0.1 s 采样）----
  // [t, x, y, rot]  主运动物体（落叶、风筝、照片、粒子群中心）
  "leaf": [[32.4, 880, 210, 0.12]],

  // ---- 确定性几何（一次性）----
  "skel": {
    "branches": [{ "pts": [[x, y]], "w": 34, "depth": 0, "phase": 1.2 }],
    "foliage":  [{ "x": 0, "y": 0, "r": 48, "phase": 2.1, "seed": 77 }]
  },
  "hills": { "far": [[x, y]], "near": [[x, y]] },

  // ---- 事件窗口（秒）----
  "flashes": [[start, peak, end, strength]],   // 闪白：三段时间 + 峰值
  "memory":  { "m1": [a, b, c, d] },           // 回忆段：淡入起止 + 淡出起止
  "scarfOn": 60.44, "scarfOff": 143.02,        // 道具出现/消失
  "anchors": { "leafT0": 32.66, "leafLand": 37.26 }
}
```

## 采样频率怎么定

| 数据 | 采样率 | 理由 |
|---|---|---|
| `env` | 0.5 s | 环境变化是秒级的，0.5 s 线性插值足够；再密只会让关键帧爆炸 |
| `cam` | 0.25 s | 运镜有加速度，0.25 s 才不抖 |
| 轨迹 | 0.08–0.1 s | 快速位移（落叶、飞散照片）必须密采，否则 AE 插值会"抄近路" |
| 几何 | 一次性 | 树/山是静态拓扑，只存顶点 |

**采样太疏的症状**：AE 预览时物体走直线、有折角、过冲。
**采样太密的代价**：`setKeys()` 调用几十万次，构建脚本跑 10 分钟。

## 确定性要求（最容易出错的地方）

`gen_data.mjs` 必须**可重复**：同输入跑两次，输出字节级一致。

- 只用固定种子 PRNG（`mulberry32` / `hash1` / `hash2`），禁用 `Math.random()`
- 若 Remotion 里用了 `mulberry32(20261024)` 生成树骨架，
  `gen_data.mjs` 里要**用同一实现、同一调用顺序**重算
- 调用顺序必须与 Remotion 完全一致：`rnd()` 的消费顺序变了，整棵树就变了
- 自检：`node gen_data.mjs && md5sum data.json`，连跑两次比对

## 从 Remotion 模块导入的写法

```js
const V = 'C:/path/to/remotion-project/src';
const { LYRICS, SEC, DURATION } = await import(pathToFileURL(path.join(V, 'cues.js')).href);
const { tracks } = await import(pathToFileURL(path.join(V, 'director.js')).href);
```

注意：

- Remotion 工程是 ESM（`"type": "module"`），直接用 `await import()`
- 用 `pathToFileURL()` 包一层，否则 Windows 盘符路径会报 `ERR_UNSUPPORTED_ESM_URL_SCHEME`
- 被导入的模块**不能有 React / Remotion 依赖**。如果它 `import { useCurrentFrame }`，
  就抽出一个纯函数版本（`director.js` 只依赖 `rng.js`，不依赖 React）
- 顶层 `await` 需要 `.mjs` 或 `"type":"module"`

## 与 AE 帧率的对齐

```
AE 合成时长(帧) = round(dur * fps)
Remotion durationInFrames = round(dur * fps)
```

两边都取 `round`，不要一边 `floor` 一边 `round`，也不要一边按秒一边按帧——
263.109 × 30 = 7893.27 → 两边都 7893，差一帧就够让配音错位。
