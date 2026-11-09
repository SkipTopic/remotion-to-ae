# 为什么不用 Lottie 做中转

每次提「Remotion 转 AE」，第一个反问都是：**为什么不走 Lottie？**

这是个合理的问题，但答案分两层，而且第一层就已经断了。

---

## 第一层：Remotion 根本导不出 Lottie

Remotion 和 Lottie 的关系是**单向的**，而且方向不是你以为的那个。

`remotion.dev/docs/third-party` 的 After Effects 一栏只写了一句话：

> After Effects — See: Lottie - Import from After Effects

`remotion.dev/docs/after-effects` 整页讲的是：**在 AE 里用 Bodymovin 导出 Lottie JSON，然后用 `@remotion/lottie` 在 Remotion 里播放。**

也就是说：

| 方向 | 有没有工具 |
|---|---|
| AE → Lottie → Remotion（播放） | ✅ `@remotion/lottie`，官方支持 |
| Remotion → Lottie（导出） | ❌ **不存在** |

`@remotion/lottie` 是个**播放器**，不是导出器。Remotion 的渲染管线最终产出的是像素帧（MP4 / 图片序列），
它没有"把 React 组件树反向序列化成 Lottie JSON"的能力——因为 Lottie 是声明式的关键帧数据，
而 Remotion 是任意 JS 代码，两者之间没有可逆映射。

**所以 `Remotion → Lottie → AE` 这条链，第一步就不存在。**

---

## 第二层：就算能导，Lottie 也装不下这支片子

假设有人写了个 Remotion → Lottie 的导出器，它能承载什么？

Lottie 的设计目标是"轻量、跨平台、能在手机上流畅播放"，所以它只实现了 AE 特性的一个**子集**：

| 能力 | Lottie | 说明 |
|---|---|---|
| 形状 / 填充 / 描边 / 变换 | ✅ | 核心能力 |
| 蒙版 / 轨道遮罩 | ✅ | |
| Trim Paths / Repeater | ✅ | |
| 基础缓动 | ✅ | 贝塞尔插值 |
| **表达式** | ❌ | Lottie 是纯数据格式，没有表达式引擎 |
| **3D 图层** | ❌ | Lottie 是 2D 格式 |
| **效果**（模糊、发光、调色、噪点） | ❌ | 极少数 layer effect 例外 |
| **AE 文字动画器**（range selector / 逐字抖动） | ❌ | 这是歌词动效的核心 |

而一支 260 秒的歌词 MV 实际需要什么：

- **47 条歌词 = 47 个 AE 文字层**，每层还有逐字入场、字距变化、强调字放大
  → 依赖文字动画器，Lottie 装不下；转成形状后文字不可再编辑，等于白转
- **218 个图层**，大量用表达式读 `ENV`/`CAM` 控制器做视差
  → 表达式是 Lottie 的死穴，全部会退化成逐帧烘焙的静态数据
- **3D 素材**（书口特写、纸堆、翻页序列）
  → Lottie 没有 3D 图层
- **`mixBlendMode` 多层叠加**（正片叠底、叠加、滤色）
  → Lottie 的混合模式支持极有限

结论：**即使打通第一层，第二层也过不去。**

---

## 那为什么不干脆"两段都渲染成视频再拼"？

因为那等于放弃"可编辑"这个前提。

如果最终产物是视频，就直接用 Remotion 渲，不需要进 AE；
如果最终产物要能在 AE 里改，就**必须让每一层以原生形式存在**——这正是本项目做的事。

中间的"半可编辑"状态（比如把文字烘成位图、把表达式烘成关键帧）是最糟的：
看起来进了 AE，实际上改一个氛围要重做一遍。

---

## 所以这条路径的正当性在哪

不是"比 Lottie 更好"，而是**Lottie 这条路在结构上不存在**：

1. Remotion 没有 Lottie 导出器，官方也没有 roadmap
2. Lottie 的格式能力装不下"文字层 + 表达式 + 3D + 混合模式"
3. 任何"烘一半、留一半"的方案都会退化成不可维护

要拿到真正可编辑的 AE 工程，只剩一条路：**从源工程的数值直接重建 AE 图层**。

这就是本项目的全部理由。

---

## 参考

- Remotion 官方第三方集成页：`https://remotion.dev/docs/third-party`
- Remotion 官方从 AE 导入指南：`https://www.remotion.dev/docs/after-effects`
- Lottie 特性支持表：`https://lottiefiles.com/supported-features`
- LottieFiles for After Effects（双向，含 Lottie → AE 导入）：`https://aescripts.com/lottiefiles/`
