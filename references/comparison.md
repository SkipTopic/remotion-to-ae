# 与现有工具的关系

写这份对比不是为了证明"我更好"，而是为了让人一眼判断 **该用哪个**。
同一个需求有五六种做法，选错比不做更贵。

> 数据截至 2026-11。star 数、版本号会变，以各自仓库为准。
> 标「未核实」的，是我没找到可靠来源，不做猜测。

---

## 总览

| 项目 | 方向 | 输入 | 取值机制 | 输出 | AE 侧可调性 |
|---|---|---|---|---|---|
| **本项目** | 代码 → AE | 结构化 Remotion 工程（纯函数） | `import` 纯函数取真值 | ExtendScript → 原生图层 | 控制器 + 表达式 |
| `export-to-ae` | 代码 → AE | 任意代码视频（HTML/Remotion/Python/MP4） | Claude 读源码推断 | ExtendScript + media/ + audio/ | 扁平关键帧 |
| `hlyl/ae_framework` | JSON → AE | 人写的 storyboard JSON | 读 JSON | Python → ExtendScript | 场景预合成 |
| `jhd3197/after-effects-automation` | 配置 → AE | Python/JSON 配置 | 读配置 | JS Bridge → ExtendScript | 模板 + Web 编辑器 |
| `Arman-Luthra/aftr` | 命令 → 运行中的 AE | MCP / REST / WebSocket 命令 | 实时驱动 | 直接改 AE 状态 | 全量（100+ 命令） |
| `Nexrender` | AE 模板 + 数据 → 渲染 | .aep + JSON job | 替换层素材 | MP4（不产出工程） | 模板预先做好 |
| `Templater` | AE 模板 + 数据 → 渲染 | .aep + 表格/JSON | 插件内 rig | MP4 | 模板预先做好 |
| `remotionui import-ae` | AE → Remotion | Lottie JSON | 解析 Lottie | Remotion TSX | 不适用（反向） |

---

## 逐个说清楚

### `export-to-ae`（npm，最接近的同类）

- **是什么**：Claude Code skill。装完在项目里 `/export-to-ae`，它读源码重建 AE 工程。
- **输出**：`ae-export/` 下 `build-comp.jsx`（ExtendScript）、`media/`（图片/logo/素材逐个独立）、
  `audio/`（每个音效拆成独立 wav）、`README.md`（含"哪些被近似了"的清单）。
- **状态**：v1.0.0，2026-10 发布，MIT，1 位维护者，周下载约 9。
  GitHub 仓库**未找到**（只在 npm 与 socket.dev 上确认存在）。
- **强项**：覆盖面广（HTML/Python/MP4 都能试）、装了就能用、**音频分层**做得好。
- **弱项**（其 README 自述）：blur / glow / 粒子 / 3D / 复杂 CSS filter **只能近似**。
- **和本项目的关系**：同定位不同策略。它低门槛有损，本项目高门槛无损。

**值得借鉴的两点**：① 音频拆成独立 wav；② 在 README 里逐条列出被近似的特性——这种诚实反而建立信任。

### `hlyl/ae_framework`（AE Explainer Framework）

- **是什么**：把一份 JSON storyboard（场景/文字/动画/时间）转成完整 AE 组合。
- **机制**：Python 校验 → 生成 ExtendScript → AE 里跑。场景预合成架构。
- **有价值的点**：**音频分析自动切场景**（分析配音自动定场景边界），以及"AI 生成 JSON → 清洗 → 校验"的流程。
- **和本项目的关系**：机制相同（JSON → jsx），但输入是人写的 JSON，不是从代码工程抽数值。
  它适合"讲清楚一件事"的解释类视频，不适合每帧都由函数驱动的片子。

### `jhd3197/after-effects-automation`

- **是什么**：Python 到 ExtendScript 的桥，带 CLI、Web 编辑器、CEP 面板、内置模板。
- **规模**：约 65 star（搜索时所见）。
- **关系**：更偏"AE 自动化中间件"，比本项目更重、更通用，但不解决"从代码取真值"这件事。

### `Arman-Luthra/aftr`（Puppeteer for After Effects）

- **是什么**：Node 控制器 → WebSocket → AE 的 CEP 面板 → 执行 ExtendScript。约 100 个命令，
  暴露成 MCP server，AI 可以直接驱动运行中的 AE。
- **亮点**：`ae_status` / `ae_list_commands` / `ae_command`；支持"渲染 → 视觉评审 → 结构化差异 → 重渲"的自纠正闭环；
  有 headless 模拟器可以脱离 AE 跑测试。
- **和本项目的关系**：**这是本项目最该抄的架构**。现在本项目是"生成 jsx → 人手动跑 → 出错贴回来"，
  `aftr` 是"AI 直接改 AE 并立刻看到结果"。闭环更紧。

### `Nexrender` / `Templater`（反向路线）

- **方向相反**：先在 AE 里做好**模板**，再用数据批量替换、批量渲染。不产出可编辑工程，产出视频。
- **规模**：Nexrender 约 1.7k star，MIT；Templater 是商业插件。
- **什么时候该用它们**：要做 500 个变体、模板固定、只换文字和图片 —— 这时候"代码生成 AE"是绕远路。
- **什么时候不该用**：动画本身要根据数据动态生成（本项目就是），模板思路装不下。

### `remotionui import-ae`（反向）

- **方向相反**：把 Lottie JSON 转成可编辑的 Remotion TSX，让 AE 动画变成代码。
- **有价值的点**：遇到不支持的特性会**明确拒绝生成并逐条列出**（`--skip-unsupported` 才降级）。
  这种"失败要响"的做法，比静默近似好得多。

---

## 怎么选（决策树）

```
你要的是可编辑工程，还是成片？
├─ 成片
│   ├─ 模板固定、只换数据 → Nexrender / Templater
│   └─ 动画随数据变 → 直接用 Remotion 渲染，别进 AE
└─ 可编辑 AE 工程
    ├─ 只是想"能改就行"，接受近似 → export-to-ae（装上就能试）
    ├─ 动画本质是数据驱动的，且要求逐帧对得上 → 本项目
    └─ 想让 AI 实时操作 AE（不产出工程） → aftr
```

---

## 本项目不做什么（免得误用）

| 不做 | 为什么 | 去哪里找 |
|---|---|---|
| 音频分层 | 目前只把原曲塞进 AE | `export-to-ae` |
| 实时驱动 AE | 只生成脚本，不接管 AE | `aftr` |
| 通用格式转换 | 依赖纯函数结构，import 不了松散工程 | `export-to-ae` |
| 批量变体渲染 | 目标是"可编辑工程"不是"批量成片" | `Nexrender` / `Templater` |
| 浏览器特有视觉的等效 | `backdrop-filter`、多层 `mixBlendMode` 仍需人工调 | 用 `verify_fidelity.py` 量化差距 |

---

## 一句话总结

**这个领域不缺"能从代码生成 AE 工程"的工具，缺的是"生成出来还能当作真工程继续维护"的方案。**

本项目赌的是：愿意在前期把 Remotion 写成纯函数的人，值得拿到一个无损的 AE 工程作为回报。
