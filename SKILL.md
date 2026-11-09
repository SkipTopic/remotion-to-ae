---
name: remotion-to-ae
description: 用 Remotion 生成程序化视频，并把 Remotion 工程转成 After Effects 原生可编辑工程（.aep，全部为可编辑的层/关键帧/表达式，不是视频贴片）。当用户提出「用 Remotion 做个视频」「Remotion 转 AE」「要能在 AE 里继续改的程序化片子」「导出 AE 可编辑工程」「MV / 科普视频先程序化生成再进 AE 精修」，或需要把已有 Remotion 工程反向重建为 AE 工程时使用。覆盖三阶段：Remotion 工程搭建与分段渲染、data.json 数值抽取、AE ExtendScript 构建脚本生成与执行。
agent_created: true
---

# Remotion → AE 可编辑工程

## 这个技能解决什么

程序化视频（Remotion / Canvas）适合批量生成与精确对时，但不适合人工精修；
AE 适合精修，但从零手 K 一部长片不现实。

本技能打通两者：**Remotion 负责"算"，AE 负责"画"**。
产出不是 MP4 贴片，而是在 AE 里能逐层选中、逐关键帧拖动、逐参数改的原生工程。

## 何时触发

- 用户要在 Remotion 里做一支片子（MV、科普、产品、信息图动画），并明确后续还要改
- 用户已有 Remotion 工程，要转成 AE 工程交给剪辑/设计同学
- 用户抱怨"Remotion 做出来的东西改不动，想进 AE 调"
- 用户要"可编辑的 AE 工程"，而不是渲染好的视频

不适用：只要一段视频、不需要二次编辑 → 直接用 Remotion 渲染即可，不必走 AE。

## 定位：它不是什么

先划清边界，避免误用，也避免和已有工具做无效竞争。

**它不是通用转换器。** `gen_data.mjs` 靠 `import` Remotion 的纯函数取值，
工程里动画一旦依赖 `useEffect`、`Math.random()`、外部请求，就 import 不了。
这是设计上的取舍，不是缺陷——换来的是数值无损。

**它不是 Lottie 的替代品。** `Remotion → Lottie → AE` 这条路在结构上不存在：
Remotion 只能**播放** Lottie（`@remotion/lottie`），不能**导出** Lottie；
即使能导，Lottie 也不支持表达式、3D 图层、AE 文字动画器。
完整论证见 `references/why-not-lottie.md`。

**它和 `export-to-ae` 是两种取舍，不是同一件事的优劣版本：**

| | `export-to-ae` 一类 | 本技能 |
|---|---|---|
| 门槛 | 任意代码视频，装上就能试 | 工程必须先写成纯函数 + 固定种子 |
| 代价 | blur / 粒子 / 3D 只能近似 | 前期要多花时间设计结构 |
| 收益 | 立刻可用 | 输出数值无损、可被控制器统一调 |

判断用哪个：**只要"能改"就够 → 用通用工具；要求逐帧对得上、还要能整体调氛围 → 用这套。**

**它不做的四件事**（要这些请找别家）：
音频分层（`export-to-ae` 有）、实时驱动运行中的 AE（`aftr` 有）、
批量变体渲染（`Nexrender` / `Templater` 有）、浏览器特有效果的自动等效
（`backdrop-filter`、多层 `mixBlendMode` 仍需人工调，用 `verify_fidelity.py` 量化差距）。

选型决策树与逐项对比见 `references/comparison.md`。

## 三条铁律

1. **不要解析 JSX 反推数值。** Remotion 工程里的运动逻辑是纯函数（`director.js`、`rng.js`、`world/*.js`）。
   在 Node 里 `import` 它们直接跑，把结果采样成数组写进 `data.json`。
   解析 JSX 源码是错的方向，会丢掉缓动、随机种子和分支。
2. **AE 表达式只做"读控制器 + 简单映射"，不做复杂计算。**
   颜色插值、季节权重、曲线混合全部在 Node 侧算完，转成关键帧数组。
   表达式里出现的应该只有 `E('Season')*13` 这种一行映射。
3. **总时长与音频必须逐帧对齐。** `data.json` 的 `dur`、`fps` 是唯一真源，
   AE 合成与 Remotion 的时间轴帧数必须一致，否则所有对时全废。

## 三阶段工作流

### 阶段 1 · 搭 Remotion 工程

目标：一个能独立渲染的 Remotion 工程，运动逻辑写成**纯函数**（给定 t 返回状态），
不依赖 React 组件副作用。这是后面能被 `import` 复用的前提。

```
proj/
├── src/
│   ├── cues.js        # 歌词/字幕时间轴 [{t, end, text}]
│   ├── segments.js    # 段落结构 [{name, t, end}]
│   ├── palette.js     # 颜色常量
│   ├── rng.js         # mulberry32 / hash / clamp / lerp / easing
│   ├── director.js    # 轨道函数：season(t) / daylight(t) / camAt(t) ...
│   └── world/         # 场景元素（每个导出纯函数或确定性构建器）
├── remotion/
│   ├── entry.jsx      # Composition：durationInFrames = round(dur*fps)
│   └── Frame.jsx      # 第 n 帧 = f(n) 的纯渲染
└── package.json
```

要点见 `references/remotion-authoring.md`。

### 阶段 2 · 抽 data.json

```bash
node scripts/gen_data.mjs        # 改顶部常量：REMOTION_SRC / OUT
```

脚本 `import` Remotion 的纯函数模块，按固定频率采样，产出单一 `data.json`：

| 字段 | 采样率 | 用途 |
|---|---|---|
| `env` | 0.5 s | 季节 / 昼夜 / 晚霞 / 风 等环境滑块 |
| `cam` | 0.25 s | 相机 x / y / zoom（视差与运镜） |
| `leaf` 等轨迹 | 0.08–0.1 s | 主运动物体的路径，AE 侧转位置关键帧 |
| `skel` / `hills` | 一次性 | 树骨架、山脊线（确定性几何） |
| `lyrics` / `sec` | — | 时间轴，用于层出现时机与时间轴标记 |

完整字段契约见 `references/data-contract.md`（含采样频率选择的理由）。

**关键约束**：凡涉及随机，必须在 Node 侧用**固定种子**重算，不能用 `Math.random()`。
如果 Remotion 里用了 `mulberry32(20261024)` 这样的种子，`gen_data.mjs` 里必须
用**同一实现、同一调用顺序**重算一遍（宁可复制十几行，也不要 import 内部私有函数）。

### 阶段 3 · 生成 JSX 并在 AE 里构建

```bash
node scripts/gen_build.mjs                 # data.json → build_xxx.jsx
# 在 AE 里：File > Scripts > Run Script File... 选 build_xxx.jsx
```

`gen_build.mjs` 输出一个约 10 万行级的 ExtendScript，负责：

1. 建合成（尺寸 / 帧率 / 时长从 `data.json` 读）
2. 建层：形状层、文本层、纯色层、预合成
3. 打关键帧：把 `data.json` 里的采样数组 `JSON.stringify` 成 `setKeys()` 调用
4. 写表达式：只写读控制器的映射式
5. 建两个引导层：`ENV`（环境滑块）/ `CAM`（运镜），全片表达式引用它们

构建函数库、层命名规范、表达式写法见 `references/ae-build-cookbook.md`。
`scripts/gen_build.mjs` 是可直接改的骨架，含 12 个核心工具函数。

**执行顺序（重要）**：先 `gen_data` → 再 `gen_build` → 再在 AE 里跑 jsx。
`build_*.jsx` 开头会 `app.newProject()` 或清空当前合成，**跑之前先存盘**。

## 渲染：先分段，再合片

渲染是这条流水线上最贵的一步。**先读 `references/rendering.md`**，核心结论：

- `--concurrency=1` 通常是 2–4 核机器上的最优解。实测 2 核 4 线程上
  `--concurrency=3` 比 `=1` 慢 **56%**（1.56 s/帧 vs 1.00 s/帧）——加并发只会互相抢。
  不要凭"并发越高越快"的直觉调大。
- **调试阶段不要渲整段样片。** 渲 30 秒样片在 2 核机器上要 15 分钟，
  改 12 版就是 3 小时。改用 `--frames=620-650` 只渲 1 秒（约 40 秒），
  或 `remotion still` 抽单帧（2–4 秒）。
- 分段渲染：每段 **≤1300 帧**，每段独立 `.done` + 实际帧数先验，
  崩了只重跑 1/N。

用 `scripts/render_segmented.sh`，已内置正确的 ffprobe 校验写法
（见下方"陷阱 3"）。

## 审核：量化扫描 + 人工抽帧

渲染完不要只看一遍就交。用 `scripts/qa_scan.py` 逐帧扫：

```bash
python scripts/qa_scan.py <video.mp4>
```

输出：纯白帧 / 近黑帧 / 连续近静止段 / 帧差=0 的帧 / 4 秒窗口表。
判读标准与二次复核方法见 `references/qa-and-acceptance.md`。

## 保真度自证：把"无损"变成数字

"同源取数是无损的"这句话，没有数字就是空话。用 `scripts/verify_fidelity.py` 拿证据：

```bash
python scripts/verify_fidelity.py remotion版.mp4 ae重建版.mp4 --top 10 --worst-dir ./diff
```

它用 ffmpeg 的 `psnr` 滤镜逐帧比对，输出平均 / 最低 / P05 / P50 dB，
列出最差 N 帧，并把连续低分聚成区间——**低分区间应该恰好落在你知道会有差异的地方**，
如果散落在全片，说明重建有问题。

判读（1080p / 30fps / 两次 H.264 编码）：

| PSNR | 含义 |
|---|---|
| > 42 dB | 几乎不可辨，编码噪声级 |
| 38–42 | 优秀 |
| 34–38 | 良好，文字边缘可能有抗锯齿差异 |
| 30–34 | 可接受，细看有差 |
| < 30 | 有明显差异，查字体 / 混合模式 / 色彩空间 |

**真实对照结果**（同一支片子，"含插帧"版 vs "不含插帧"版，7893 帧）：

```
PSNR 平均 48.10 dB / 最低 13.33 dB / 低于 35 dB 的帧 40（0.51%）
低分区间：4441–4476（148.03s–149.20s）← 正是插入镜头的帧段
```

说明两件事：① 除了那 1.2 秒，全片差异在编码噪声级别；
② 这个脚本不会瞎报警，只指出真正不同的地方。

**注意**：字体光栅化、抗锯齿、色彩管理在两个渲染器里本来就不同，
这类差异集中在文字边缘，属于预期，不要当 bug 追。H.264 双边各编一次，
理论上限通常封顶在 45–48 dB，不要期待无穷大。

## 十个最常翻车的点

完整版见 `references/pitfalls.md`，先记住这十条：

1. **`TransitionSeries` 会吃掉总时长**：Σ各段 − Σ转场。必须做补偿恒等式
   `ΣS = D + ΣT`，并在代码里断言总帧数，不等就抛错。
2. **颗粒/噪点层按秒换纹理 = 死帧**：`Math.floor(frame/30)%3` 会让同一秒内 30 帧
   像素完全相同。改 `frame%3` 并叠位移抖动。
3. **Node 的 `execSync` 不认 MSYS 路径**：`/c/Users/...` 传给原生 exe 会报
   `No such file or directory`。bash 直调会自动转换，Node 不会。
   校验帧数一律用 bash 直调 ffprobe + `tr -d ' ,'`。
4. **"到下一句的间隔" ≠ "这句唱多久"**：把前者当 `dur` 会让一句话撑 20 秒，
   文字落定后 20 秒无事可做 → 大面积死帧。间奏要单独建分镜序列。
5. **随机旋转会让并排两张图同向**：`rng()*5-2.5` 是随机的，
   要并排反向就按位置显式传 `rot`：左侧负、右侧正。
6. **文字基准和图片基准取同一个百分比 = 必然重叠**：文字 52%、图片 52%，
   文字一定压住图片下缘。给两者留 ≥48px 硬间距。
7. **生图工具的 `background:"transparent"` 可能不生效**：实际返回 RGB。
   抠图用 HSV 的 V/S 双判据（明度 + 饱和度），不要用"与背景色差"，
   否则主体高光会被判成背景。见 `scripts/cutout_bg.py`。
8. **素材要过"可辨文字"筛**：商业招牌、清晰书封、门牌、价签入画等于画面里出现字，
   必须排除。同时排除高饱和大色块。
9. **`--concurrency` 不是越大越快**，见上。
10. **AE 表达式冷启动**：工程刚打开时元素错位是表达式未求值，
    拖一下时间指针或按空格预览即恢复。不要以为工程坏了去重建。

## 资源索引

| 文件 | 用途 |
|---|---|
| `README.md` | 项目定位、与现有工具的对比、边界（给人看的入口） |
| `references/data-contract.md` | `data.json` 完整字段契约、采样率选择、确定性要求 |
| `references/remotion-authoring.md` | Remotion 工程结构与纯函数约束、分段渲染、调试节奏 |
| `references/ae-build-cookbook.md` | ExtendScript 工具函数、层命名、表达式与控制器规范、AE 侧坑 |
| `references/rendering.md` | 渲染性能实测、分段策略、崩溃恢复 |
| `references/qa-and-acceptance.md` | 量化审核指标、二次复核、验收清单 |
| `references/pitfalls.md` | 29 条实战翻车点与修法 |
| `references/comparison.md` | 与 export-to-ae / ae_framework / aftr / Nexrender 的逐项对比 + 选型决策树 |
| `references/why-not-lottie.md` | 为什么 Lottie 中转在结构上不成立（两层论证） |
| `scripts/gen_data.mjs` | 阶段 2 模板：从 Remotion 模块采样出 `data.json` |
| `scripts/gen_build.mjs` | 阶段 3 骨架：`data.json` → AE ExtendScript，含 12 个工具函数 |
| `scripts/render_segmented.sh` | 分段渲染 + 帧数先验 + 正确 ffprobe 校验 |
| `scripts/qa_scan.py` | 逐帧量化审核（纯白/近黑/近静止/帧差=0） |
| `scripts/verify_fidelity.py` | 逐帧 PSNR 比对，量化"重建保真度" |
| `scripts/cutout_bg.py` | 浅色底素材抠透明 PNG（V/S 双判据） |
| `scripts/prepare_ai.py` | 去平台水印 + 尺寸校准 |

## 验收清单

交付前逐条确认：

- [ ] `data.json` 的 `dur` × `fps` == AE 合成时长帧数 == Remotion `durationInFrames`
- [ ] AE 工程里所有层命名符合规范，`ENV` / `CAM` 两个引导层存在且未被渲染开关关闭
- [ ] 随机性全部由固定种子驱动，重跑 `gen_data.mjs` 两次输出的 `data.json` 完全一致
- [ ] 成片总帧数与目标一致，纯白帧 0，连续近静止段 ≤3 且合计 <1.5%
- [ ] 抽 10 个关键时间点人工核对：文字可读、素材无违禁元素、转场非硬切
- [ ] `build_*.jsx` 能在干净的 AE 工程里一趟跑完不报错（先存盘再跑）
- [ ] `verify_fidelity.py` 比对 Remotion 版与 AE 版：平均 PSNR ≥ 38 dB，且低分区间只落在已知差异处
