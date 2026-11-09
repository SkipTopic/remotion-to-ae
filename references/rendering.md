# 渲染：性能实测与分段策略

渲染是整条流水线最贵的一步。一部长片（260 s / 7893 帧）在 2 核机器上要 2 小时以上，
一次崩溃就全废。本文记录实测数据与可靠做法。

## 实测：并发不是越大越快

同一工程、同一机器（2 核 4 线程、无 GPU、Chrome + ANGLE 软渲染）：

| 配置 | 120 帧耗时 | 单帧耗时 | 结论 |
|---|---|---|---|
| `--concurrency=1` | ~120 s | **1.00 s/帧** | ✅ 最优 |
| `--concurrency=3` | 187 s | **1.56 s/帧** | ❌ 慢 56% |

原因：多开标签页会让多个 Chrome 进程抢同样的 CPU 与内存，加上 1080p 合成本身就吃满核，
并发只增加切换开销。

> 通用建议：`--concurrency` 取 **物理核数的一半到一倍**，且必须实测。
> 在无 GPU 的机器上，默认就从 1 开始试，不要从 8 往下调。

## 真正的浪费：反复渲整段样片

一次真实事故的时间账：

| 时段 | 在干什么 | 耗时 |
|---|---|---|
| 13:51–16:42 | **12 个 30 秒样片**（一版一个） | **2 h 51 min（占 55%）** |
| 16:43–18:47 | 正片 3 段 | 1 h 53 min |
| 18:47–19:02 | 第 4 段渲到 855/1893 崩溃 | 15 min 白费 |

5 小时里一半以上花在"改一版渲一遍 30 秒"，正片反而没出完。

**规矩**：调试期只渲 1 秒片段。

```bash
# 只看第 620–650 帧（约 1 秒）
node node_modules/@remotion/cli/remotion-cli.js render \
  remotion/entry.jsx CompId out/preview.mp4 --frames=620-650 --concurrency=1

# 只看单帧
node node_modules/@remotion/cli/remotion-cli.js still \
  remotion/entry.jsx CompId out/still.png --frame=400
```

## 分段渲染

每段 **≤1300 帧**。2000 帧一段在渲染中途 Chrome 崩一次就整段重来。

```bash
# 7893 帧 → 6 段
seg 1    0-1315
seg 2 1316-2631
seg 3 2632-3947
seg 4 3948-5263
seg 5 5264-6579
seg 6 6580-7892
```

用 `scripts/render_segmented.sh`，它做了四件正确的事：

1. 每段先查 `.frames` 先验文件（内容 = 实际帧数），对得上才跳过
2. 渲完立刻校验帧数，不等就退出
3. 校验通过才写 `.done`
4. 全部完成后才 concat + 混音

### 帧数校验的写法（这里有坑）

```bash
# ✅ 正确：bash 直调 ffprobe，MSYS 会自动把 /c/ 转成 C:/
nb=$(ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames \
      -of csv=p=0 "$OUT/seg1.mp4" | tr -d ' ,')
[ "$nb" = "1316" ] || { echo "FRAME MISMATCH: $nb"; exit 1; }

# ❌ 错误：Node 的 execSync 走 cmd.exe，不做路径转换
node -e "execSync('ffprobe ... \"/c/Users/x/seg1.mp4\"')"
# → ffprobe 报 No such file or directory，文件明明存在
```

注意 `-of csv=p=0` 的输出带尾随逗号（`1316,`），必须 `tr -d ' ,'`。

## 崩溃恢复

- 崩溃后先查有没有僵尸 `ffmpeg.exe` / `chrome.exe` 占着内存
- `--timeout=180000` 让某一帧卡死时能报错退出，而不是无限等
- 每段独立，崩了只重跑那一段

## 合片与混音

```bash
ffmpeg -y \
  -i out/seg1.mp4 -i out/seg2.mp4 ... -i out/seg6.mp4 \
  -i "原曲.flac" \
  -filter_complex "[0:v][1:v][2:v][3:v][4:v][5:v]concat=n=6:v=1:a=0[v];[4:a]aresample=48000[a]" \
  -map "[v]" -map "[a]" -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p \
  -c:a aac -b:a 256k -ar 48000 -shortest \
  out/full.mp4
```

- `-shortest` 防止音频比视频长导致尾部黑帧
- `-crf 18` 对静态为主的画面足够；照片细节多可以降到 16
- 输出响度建议校验：`ffmpeg -i full.mp4 -af ebur128=peak=true -f null -`
  （注意不要加 `-v error`，否则滤波器输出被吞）
  上平台一般归一到 `-14 LUFS`，本地留存可保持母带原样

## 还能再快的手段

| 手段 | 预期收益 | 代价 |
|---|---|---|
| 图片预缩放（2400 → 1280 长边） | 10–25% | 一次性生成一套 `photos_r/` |
| 模糊底图预渲染成静态 JPG | 10–20% | 需改代码，把每帧 `blur()` 换成贴图 |
| `--jpeg-quality=85`（默认 95） | 5–10% | 肉眼几乎无差 |
| 减少 `mixBlendMode` 嵌套层数 | 5–15% | 需重构视觉层 |

软件渲染下 `blur()`、`backdrop-filter`、多层 `mixBlendMode` 是最贵的三个属性，
能用静态图替代就别每帧算。
