#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""qa_scan.py —— 逐帧量化审核。只读，不改任何视频。

用法：
    python qa_scan.py <video.mp4> [--fps 30]

输出指标（判读标准见 references/qa-and-acceptance.md）：
    纯白帧 / 近黑帧 / 帧差=0 完全冻结 / 连续 ≥10 帧近静止 / 4 秒窗口表

注意：本脚本在 192×108 上跑，速度快但会平均掉细微运动。
凡是要下"这段是死的"结论，必须用 960×540 复核一次（脚本末尾给出复核写法）。
"""
import argparse
import subprocess
import sys

import numpy as np

W, H = 192, 108


def read_gray(src, w=W, h=H):
    cmd = ["ffmpeg", "-v", "error", "-i", src,
           "-vf", f"scale={w}:{h},format=gray",
           "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    buf = subprocess.run(cmd, capture_output=True).stdout
    n = len(buf) // (w * h)
    return np.frombuffer(buf[: n * w * h], dtype=np.uint8).reshape(n, h, w).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()
    fps = args.fps

    f = read_gray(args.video)
    n = f.shape[0]
    print(f"frames read = {n}")

    flat = f.reshape(n, -1)
    mean = flat.mean(axis=1)
    std = flat.std(axis=1)
    d = np.concatenate([[0.0], np.abs(np.diff(flat, axis=0)).mean(axis=1)])

    print(f"luma mean  : avg={mean.mean():.2f} min={mean.min():.2f} max={mean.max():.2f}")
    print(f"luma std   : avg={std.mean():.2f} min={std.min():.2f} max={std.max():.2f}")
    print(f"frame diff : avg={d.mean():.3f} median={np.median(d):.3f} "
          f"p10={np.percentile(d, 10):.3f} p90={np.percentile(d, 90):.3f} max={d.max():.2f}")

    white = np.where((mean > 236) & (std < 3.2))[0]
    print(f"\n[纯白帧] {len(white)} 帧" + (f" -> {white[:40].tolist()}" if len(white) else ""))

    black = np.where(mean < 12)[0]
    print(f"[近黑帧 mean<12] {len(black)} 帧" + (f" -> {black[:40].tolist()}" if len(black) else ""))

    frozen = np.where(d < 1e-6)[0]
    print(f"[帧差=0 完全冻结] {len(frozen)} 帧" + (f" -> {frozen[:30].tolist()}" if len(frozen) else ""))

    still = d < 0.35
    runs, i = [], 0
    while i < n:
        if still[i]:
            j = i
            while j < n and still[j]:
                j += 1
            if j - i >= 10:
                runs.append((i, j - 1, j - i))
            i = j
        else:
            i += 1
    tot = sum(r[2] for r in runs)
    print(f"\n[连续>=10帧 近静止] {len(runs)} 段, 合计 {tot} 帧 ({tot/max(n,1)*100:.1f}%)")
    for a, b, L in sorted(runs, key=lambda x: -x[2])[:15]:
        print(f"  frames {a}-{b}  ({a/fps:7.2f}s-{b/fps:7.2f}s)  len={L} ({L/fps:.2f}s)")

    jump = [int(j) for j in np.where(d > 45)[0] if 6 < j < n - 12]
    print(f"\n[帧差>45 的硬跳变] {len(jump)} 处 -> {jump[:30]}")

    win = fps * 4
    print("\n[4秒窗口] idx  start-end     mean   std   diff_avg  maxdiff")
    for k in range(0, n, win):
        a, b = k, min(k + win, n)
        m, s, dm, dx = mean[a:b].mean(), std[a:b].mean(), d[a:b].mean(), d[a:b].max()
        flag = ""
        if m > 232:
            flag += " <<WHITE"
        if m < 18:
            flag += " <<DARK"
        if dm < 0.5:
            flag += " <<DEAD"
        print(f"  {k//win:3d} {a:5d}-{b:5d}  {m:6.1f} {s:5.1f}  {dm:7.3f}  {dx:6.2f}{flag}")

    print("""
---
复核提示：上面的「近静止」在 192x108 上算，可能把缓推平均掉。
对可疑区间用 960x540 复算：
    a = read_gray(src, 960, 540)[t0:t1]
    d = np.abs(np.diff(a, axis=0)).mean(axis=(1, 2))
帧差 0.001-0.02 → 真死；0.3-1.0 → 有极缓运动，可接受。
""")


if __name__ == "__main__":
    sys.exit(main())
