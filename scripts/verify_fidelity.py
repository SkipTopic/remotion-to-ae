#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""verify_fidelity.py —— 逐帧比对两条视频，量化"重建保真度"。

用途：证明「AE 重建版」和「Remotion 原版」在像素层面到底差多少。
     这是"同源取数"区别于"源码推断"的唯一硬证据。

用法：
    python verify_fidelity.py <a.mp4> <b.mp4> [--top 10] [--json report.json]
                              [--worst-dir DIR] [--psnr-fail 35]

输出：
    整体 PSNR / 每帧 PSNR 分布 / 低于阈值的帧数 / 最差 N 帧（帧号 + 时间 + dB）
    可选：把最差的几帧导出成并排对比图，直接看差在哪

怎么读（经验值，1080p 30fps，两次 H.264 编码）：
    > 42 dB   几乎不可辨，编码噪声级别
    38–42     优秀，肉眼需逐帧对比才能发现
    34–38     良好，静态看无异，运动时有细微差别（抗锯齿/字体渲染）
    30–34     可接受，细看有差（常见于文字抗锯齿策略不同）
    < 30      有明显差异，检查字体、混合模式、色彩空间

注意：
    1. 两边必须是"同源同帧"才有意义。帧率不同会直接失败。
    2. H.264 本身有损，所以理论最大值不是无穷大——双边各编一次，通常封顶在 45–48 dB。
    3. 这里的差异不全是 bug。字体光栅化、抗锯齿、色彩管理在两个渲染器里本来就不同，
       这类差异集中在文字边缘，属于预期。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile


def ffprobe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate,nb_frames",
         "-of", "default=nw=1", path],
        capture_output=True, text=True,
    ).stdout
    d = {}
    for line in out.strip().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k] = v
    return d


def check(path):
    if not os.path.exists(path):
        sys.exit(f"文件不存在: {path}")
    s = ffprobe(path)
    if not s:
        sys.exit(f"读不到视频流: {path}")
    num, den = (s.get("r_frame_rate", "0/1").split("/") + ["1"])[:2]
    fps = float(num) / float(den or 1)
    return {
        "w": int(s.get("width", 0)),
        "h": int(s.get("height", 0)),
        "fps": fps,
        "frames": int(s["nb_frames"]) if s.get("nb_frames", "N/A").isdigit() else None,
    }


def run_psnr(a, b, tmpdir):
    """用 ffmpeg 的 psnr 滤镜拿每帧 dB。

    坑：滤镜参数里的 Windows 绝对路径会被 `:` 和 `\\` 解析坏
    （`stats_file=C:\\Users\\...` → 报 "Unable to parse option value"）。
    解法：在 tmpdir 里用相对文件名，并把输入路径转成绝对路径后跑。
    """
    log = os.path.join(tmpdir, "psnr.log")
    a, b = os.path.abspath(a), os.path.abspath(b)
    vf = ("[0:v]scale=iw:ih,setsar=1,setpts=PTS-STARTPTS[x];"
          "[1:v]scale=iw:ih,setsar=1,setpts=PTS-STARTPTS[y];"
          "[x][y]psnr=stats_file=psnr.log")
    cmd = ["ffmpeg", "-v", "error", "-i", a, "-i", b,
           "-lavfi", vf, "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=tmpdir)
    if not os.path.exists(log):
        sys.exit("psnr 滤镜未产出日志，可能是两边帧率/尺寸差异过大：\n" + (r.stderr or "")[:800])
    rows = []
    pat = re.compile(r"n:\s*(\d+).*?psnr_avg:([\d.inf]+)")
    with open(log, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = pat.search(line)
            if m:
                n = int(m.group(1))
                v = m.group(2)
                rows.append((n, float("inf") if v == "inf" else float(v)))
    return rows


def side_by_side(a, b, frame, fps, outdir):
    """把某一帧从两条视频里抽出来拼一张对比图。"""
    t = frame / fps
    os.makedirs(outdir, exist_ok=True)
    pa = os.path.join(outdir, f"_a_{frame}.png")
    pb = os.path.join(outdir, f"_b_{frame}.png")
    for src, dst in ((a, pa), (b, pb)):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", src,
                        "-frames:v", "1", dst], capture_output=True)
    out = os.path.join(outdir, f"diff_frame_{frame}.jpg")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", pa, "-i", pb,
                    "-filter_complex", "[0:v][1:v]hstack=inputs=2",
                    "-q:v", "3", out], capture_output=True)
    for p in (pa, pb):
        try:
            os.remove(p)
        except OSError:
            pass
    return out if os.path.exists(out) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a", help="参考视频（如 Remotion 原版）")
    ap.add_argument("b", help="待测视频（如 AE 重建版）")
    ap.add_argument("--top", type=int, default=10, help="列出最差 N 帧")
    ap.add_argument("--json", default="", help="把结果写成 JSON")
    ap.add_argument("--worst-dir", default="", help="把最差帧导出成并排对比图")
    ap.add_argument("--psnr-fail", type=float, default=35.0, help="低于此 dB 视为不达标")
    args = ap.parse_args()

    ia, ib = check(args.a), check(args.b)
    print(f"A: {ia['w']}x{ia['h']} {ia['fps']:.3f}fps frames={ia['frames']}")
    print(f"B: {ib['w']}x{ib['h']} {ib['fps']:.3f}fps frames={ib['frames']}")

    if abs(ia["fps"] - ib["fps"]) > 0.01:
        sys.exit(f"帧率不一致（{ia['fps']} vs {ib['fps']}），无法逐帧比对")
    if ia["frames"] and ib["frames"] and ia["frames"] != ib["frames"]:
        print(f"!! 帧数不一致，按较短的比对：{min(ia['frames'], ib['frames'])} 帧")

    with tempfile.TemporaryDirectory() as td:
        rows = run_psnr(args.a, args.b, td)

    if not rows:
        sys.exit("没有解析到 PSNR 数据")

    vals = [v for _, v in rows if v != float("inf")]
    finite = [v for v in vals if v > 0]
    fps = ia["fps"] or 30.0
    n = len(rows)

    avg = sum(finite) / len(finite) if finite else 0
    worst = sorted(rows, key=lambda r: r[1])[: args.top]
    below = [r for r in rows if r[1] < args.psnr_fail]

    print(f"\n比对帧数: {n}")
    print(f"PSNR 平均 : {avg:.2f} dB")
    print(f"PSNR 最低 : {min(v for _, v in rows):.2f} dB")
    if finite:
        s = sorted(finite)
        print(f"PSNR P05  : {s[int(len(s)*0.05)]:.2f} dB")
        print(f"PSNR P50  : {s[len(s)//2]:.2f} dB")
    print(f"低于 {args.psnr_fail} dB 的帧: {len(below)} / {n} ({len(below)/max(n,1)*100:.2f}%)")

    # 判定
    if avg >= 42:
        verdict = "几乎不可辨（编码噪声级）"
    elif avg >= 38:
        verdict = "优秀"
    elif avg >= 34:
        verdict = "良好（文字边缘可能有细微抗锯齿差异）"
    elif avg >= 30:
        verdict = "可接受，细看有差"
    else:
        verdict = "有明显差异，检查字体/混合模式/色彩空间"
    print(f"结论      : {verdict}")

    print(f"\n最差 {len(worst)} 帧：")
    print("  frame   time(s)    PSNR(dB)")
    for fr, v in worst:
        print(f"  {fr:5d}  {fr/fps:8.3f}   {v:7.2f}")

    if below:
        # 连续低帧聚成区间，便于定位"是哪一段坏了"
        idx = sorted(r[0] for r in below)
        segs, st = [], idx[0]
        for i in range(1, len(idx)):
            if idx[i] != idx[i - 1] + 1:
                segs.append((st, idx[i - 1]))
                st = idx[i]
        segs.append((st, idx[-1]))
        print(f"\n低分区间（{len(segs)} 段，前 10）：")
        for a_, b_ in segs[:10]:
            print(f"  {a_}-{b_}  ({a_/fps:.2f}s-{b_/fps:.2f}s)  {b_-a_+1} 帧")

    made = []
    if args.worst_dir:
        for fr, _ in worst[:5]:
            p = side_by_side(args.a, args.b, fr, fps, args.worst_dir)
            if p:
                made.append(p)
        if made:
            print(f"\n并排对比图已导出：{args.worst_dir}（{len(made)} 张）")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({
                "a": args.a, "b": args.b,
                "frames": n, "fps": fps,
                "psnr_avg": round(avg, 3),
                "psnr_min": round(min(v for _, v in rows), 3),
                "below_threshold": len(below),
                "threshold": args.psnr_fail,
                "verdict": verdict,
                "worst": [{"frame": fr, "time": round(fr / fps, 3), "psnr": round(v, 2)} for fr, v in worst],
                "images": made,
            }, f, ensure_ascii=False, indent=1)
        print(f"JSON 报告：{args.json}")


if __name__ == "__main__":
    sys.exit(main())
