# remotion-to-ae

**Turn a Remotion project into a native, fully editable After Effects comp — with zero approximation.**

**把 Remotion 工程无损重建为 AE 原生可编辑工程。**

Not a video paste-in. Every layer is a real AE layer, every keyframe is draggable, and the whole
comp is driven by two controller layers (`ENV` / `CAM`) instead of hundreds of scattered keys.

不是视频贴片。每一层都是真正的 AE 图层，每个关键帧都能拖，整个合成由两个控制器层
（`ENV` / `CAM`）驱动，而不是散落在各处的几百个关键帧。

[English](#english) · [中文](#chinese) · [SKILL.md](SKILL.md)

---

<a id="english"></a>
## English

### The problem

Programmatic video (Remotion) is great at deterministic timing and batch generation, but painful to
refine by hand. After Effects is great at refinement, but hand-keying a long-form piece is not viable.

Existing tools (`export-to-ae`, `ae_framework`, …) take an **inferential** route: they read your
source code and guess what each layer is and where its animation came from. That is inherently lossy —
CSS `filter`, particles, 3D and `mixBlendMode` can only be *approximated*.

This project takes a **same-source** route: Remotion's motion logic is already pure functions. Import
them in Node, run them, sample the real values into `data.json`, and let AE only draw.

```
Remotion computes  →  data.json  →  ExtendScript  →  native AE comp
(pure functions)      (one interface)  (layers / keys / expressions)
```

**The cost is a constraint**: your Remotion project must be written as pure functions with fixed
seeds. That is a trade-off, not a free lunch.

### Relationship to existing tools

Not a competitor — a different trade-off.

| | `export-to-ae` style | This project |
|---|---|---|
| Input | Any code video (HTML / Remotion / Python / MP4) | A structured Remotion project (pure functions) |
| Value sourcing | Inferred from source code | Imported from pure functions |
| Fidelity | blur / particles / 3D approximated (self-documented) | Frame-accurate; verifiable via `verify_fidelity.py` |
| AE shape | Flat keyframes | Controllers (`ENV` 15 sliders + `CAM`) + expressions |
| Onboarding | Install and try | Restructure your project first |
| Good for | One-off exports, loosely structured projects | Long-lived pieces with repeated mood tweaks |

Full comparison: [`references/comparison.md`](references/comparison.md).

### Why not Lottie

The official Remotion docs (`remotion.dev/docs/third-party`) list exactly one After Effects
integration: **AE → Lottie → Remotion** (one direction). `@remotion/lottie` is a *player*, not an
exporter — there is no Remotion → Lottie path.

And even if there were, Lottie only covers a subset of AE: no expressions, no 3D layers, no AE text
animators. A 47-line lyric video alone disqualifies it.

Full argument: [`references/why-not-lottie.md`](references/why-not-lottie.md).

### Quick start

```bash
# 1. Sample values (edit SRC at the top of gen_data.mjs)
node scripts/gen_data.mjs

# 2. Generate the AE build script (edit OUT_AEP / font in gen_build.mjs)
node scripts/gen_build.mjs

# 3. In AE: File > Scripts > Run Script File... pick build.jsx
#    WARNING: the script wipes the current project. Save first.
```

Rendering and acceptance:

```bash
bash scripts/render_segmented.sh 7893 1316            # segmented render + frame-count guard
python scripts/qa_scan.py out/full.mp4                # frame-wise QA
python scripts/verify_fidelity.py remotion.mp4 ae.mp4 # fidelity proof
```

### Dependencies

| Component | Version | Used by |
|---|---|---|
| Node.js | 18+ | `gen_data.mjs`, `gen_build.mjs` |
| Python | 3.9+, with `Pillow` and `numpy` | `qa_scan`, `verify_fidelity`, `cutout_bg`, `prepare_ai` |
| ffmpeg / ffprobe | on `PATH` | frame extraction, PSNR, segment checks |
| Adobe After Effects | 2024+ (tested on 24.1) | running `build.jsx` |

```bash
pip install pillow numpy
```

No `opencv`, no `rembg` — background removal is pure numpy.

### What's inside

```
SKILL.md                       agent entry point (workflow / rules / acceptance)
references/
  data-contract.md             data.json schema, sampling rates, determinism
  remotion-authoring.md        project structure and pure-function constraints
  ae-build-cookbook.md         12 ExtendScript helpers, controllers, AE gotchas
  rendering.md                 concurrency benchmarks, segmentation, recovery
  qa-and-acceptance.md         metric interpretation, re-verification, checklist
  pitfalls.md                  29 field-tested failure modes
  comparison.md                full comparison with existing tools
  why-not-lottie.md            why the Lottie route does not exist
scripts/
  gen_data.mjs                 stage 2: sample from Remotion modules
  gen_build.mjs                stage 3: data.json → ExtendScript
  render_segmented.sh          segmented rendering
  qa_scan.py                   frame-wise quantitative QA
  verify_fidelity.py           frame-wise PSNR between two renders
  cutout_bg.py                 background removal (V/S dual criteria)
  prepare_ai.py                watermark removal + size normalisation
```

### Measured numbers

Same machine, 2 cores / 4 threads, no GPU, 1080p30, 7893 frames:

| Item | Measured |
|---|---|
| `--concurrency=1` | 1.00 s/frame |
| `--concurrency=3` | 1.56 s/frame (**56% slower**; CPU already saturated) |
| 30-second preview | ~15 min (this is why you should never preview whole segments) |
| 1-second slice (`--frames`) | ~40 s |
| Single still (`still`) | 2–4 s |

Fidelity check on a 7893-frame piece (two versions differing only by one inserted shot):

```
PSNR avg 48.10 dB ｜ frames below 35 dB: 40 (0.51%)
low-range frames 4441–4476 (148.03–149.20 s) ← exactly the inserted shot
```

### Boundaries

- ❌ No audio layer separation. The soundtrack goes in as a single track.
- ❌ Does not drive a running AE instance. You run the jsx manually.
- ❌ Not a general converter. Requires the pure-function project structure.
- ❌ Does not guarantee lossless for every visual. Multi-layer `mixBlendMode` and
  `backdrop-filter` still need manual equivalents; use `verify_fidelity.py` to quantify the gap.

---

<a id="chinese"></a>
## 中文

### 它解决什么问题

程序化视频（Remotion）适合精确对时与批量生成，但改不动；AE 适合精修，但从零手 K 一部长片不现实。

现有工具（`export-to-ae`、`ae_framework` 等）走的是**逆向推断**：读你的源码，猜哪层是什么、
动画从哪来。这必然有损——CSS `filter`、粒子、3D、`mixBlendMode` 只能**近似**。

本项目的路线是**同源取数**：Remotion 的运动逻辑本来就是纯函数，在 Node 里 `import` 跑，
把真值采样成 `data.json`，AE 侧只负责画。

```
Remotion 算  →  data.json  →  ExtendScript  →  AE 原生工程
（纯函数取真值）  （唯一接口）      （层 / 关键帧 / 表达式）
```

**代价是门槛**：你的 Remotion 工程必须按「纯函数 + 固定种子」写。这是取舍，不是免费午餐。

### 和现有方案的关系

不是竞争，是另一种取舍。

| | `export-to-ae` 一类 | 本项目 |
|---|---|---|
| 输入 | 任意代码视频（HTML/Remotion/Python/MP4） | 结构化的 Remotion 工程（纯函数） |
| 取值方式 | 读源码推断 | `import` 纯函数取真值 |
| 保真度 | blur/粒子/3D 近似（作者自述） | 逐帧对齐，可用 `verify_fidelity.py` 验证 |
| AE 侧形态 | 扁平关键帧 | 控制器（`ENV` 15 滑块 + `CAM`）+ 表达式 |
| 上手成本 | 装上就能试 | 先改工程结构 |
| 适合 | 一次性导出、结构松散的项目 | 长期维护、需要反复调氛围的片子 |

完整对比见 [`references/comparison.md`](references/comparison.md)。

### 为什么不用 Lottie

Remotion 官方文档（`remotion.dev/docs/third-party`）的 After Effects 一栏只给了一条路：
**AE → Lottie → Remotion**（单向）。`@remotion/lottie` 是**播放器不是导出器**，
Remotion 根本没有 Lottie 导出。

即使能导，Lottie 也不支持表达式、3D 图层、AE 文字动画器。一支 47 句歌词的 MV 光「文字层」
这一条就把它排除了。

完整论证见 [`references/why-not-lottie.md`](references/why-not-lottie.md)。

### 快速开始

```bash
# 1. 抽数值（改 gen_data.mjs 顶部的 SRC）
node scripts/gen_data.mjs

# 2. 生成 AE 构建脚本（改 gen_build.mjs 顶部的 OUT_AEP / 字体）
node scripts/gen_build.mjs

# 3. 在 AE 里：File > Scripts > Run Script File... 选 build.jsx
#    ⚠️ 脚本开头会清空当前工程，先存盘
```

渲染与验收：

```bash
bash scripts/render_segmented.sh 7893 1316            # 分段渲染 + 帧数先验
python scripts/qa_scan.py out/full.mp4                # 逐帧量化审核
python scripts/verify_fidelity.py remotion.mp4 ae.mp4 # 保真度自证
```

### 依赖

| 组件 | 版本 | 用在哪 |
|---|---|---|
| Node.js | 18+ | `gen_data.mjs`、`gen_build.mjs` |
| Python | 3.9+，需 `Pillow`、`numpy` | `qa_scan`、`verify_fidelity`、`cutout_bg`、`prepare_ai` |
| ffmpeg / ffprobe | 在 `PATH` 里 | 抽帧、PSNR、分段校验 |
| Adobe After Effects | 2024+（实测 24.1） | 跑 `build.jsx` |

```bash
pip install pillow numpy
```

不需要 `opencv`、不需要 `rembg`——抠图是纯 numpy 实现的。

### 仓库内容

```
SKILL.md                       AI agent 入口（流程 / 铁律 / 验收）
references/
  data-contract.md             data.json 字段契约、采样率、确定性
  remotion-authoring.md        工程结构与纯函数约束
  ae-build-cookbook.md         12 个 ExtendScript 工具函数、控制器、AE 坑
  rendering.md                 并发实测、分段策略、崩溃恢复
  qa-and-acceptance.md         指标判读、复核方法、验收表
  pitfalls.md                  29 条实战翻车点
  comparison.md                与现有工具的完整对比
  why-not-lottie.md            Lottie 路线为何不成立
scripts/
  gen_data.mjs                 阶段 2：从 Remotion 模块采样
  gen_build.mjs                阶段 3：data.json → ExtendScript
  render_segmented.sh          分段渲染
  qa_scan.py                   逐帧量化审核
  verify_fidelity.py           两版渲染之间的逐帧 PSNR
  cutout_bg.py                 抠图（V/S 双判据）
  prepare_ai.py                去水印 + 尺寸校准
```

### 实测数字

同一台 2 核 4 线程、无 GPU 的机器，1080p 30fps，7893 帧：

| 项 | 实测 |
|---|---|
| `--concurrency=1` | 1.00 s/帧 |
| `--concurrency=3` | 1.56 s/帧（**慢 56%**，CPU 已饱和） |
| 渲 30 秒样片 | 约 15 分钟（所以调试不该渲整段） |
| 渲 1 秒片段（`--frames`） | 约 40 秒 |
| 单帧静帧（`still`） | 2–4 秒 |

7893 帧成片的保真度对照（两版只差一个插入镜头）：

```
PSNR 平均 48.10 dB ｜ 低于 35 dB 的帧 40 个（0.51%）
低分区间 4441–4476（148.03–149.20s）← 正是那个插入镜头
```

### 边界

- ❌ 不处理音频分层。原曲整轨塞进 AE。
- ❌ 不驱动运行中的 AE。jsx 需要手动跑。
- ❌ 不是通用转换器。工程必须按纯函数规范写。
- ❌ 不保证所有视觉元素无损。多层 `mixBlendMode`、`backdrop-filter` 仍需人工调等效做法，
  用 `verify_fidelity.py` 量化差距。

---

## License

MIT. See [LICENSE](LICENSE). No assets included. The example font (ZCOOL XiaoWei) is OFL-licensed
and must be installed separately.

MIT 许可，见 [LICENSE](LICENSE)。仓库不含任何素材。示例中提到的字体（站酷小薇）为 OFL 授权，需自行安装。
