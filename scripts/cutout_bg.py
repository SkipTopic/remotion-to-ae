#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""cutout_bg.py —— 把浅色纯背景的主体抠成透明 PNG（V/S 双判据）。

用法：
    python cutout_bg.py <input.png> <output.png> [--v-cut 0.795] [--s-cut 0.135] [--feather 1.2]

为什么不用"与背景色差"：
    主体高光（掌心、金属反光、白瓷）与浅色背景的亮度太接近，色差法会把高光判成背景，
    导致主体内部出现半透明斑块、深色底上一圈白晕。

改用 HSV 的 V（明度）与 S（饱和度）双判据，实测分离度很高：
    浅米色纸背景  V 0.84-0.87 / S 0.05-0.12
    暖褐肤色主体  V 0.22-0.67 / S 0.25-0.40
    alpha = max( clip((v_cut - V)/band), clip((S - s_cut)/band) )

依赖：Pillow + numpy（不需要 cv2 / rembg）。
"""
import argparse
import sys

import numpy as np
from PIL import Image, ImageFilter

V_BAND = 0.075
S_BAND = 0.085


def blur(arr, r):
    g = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))
    return np.asarray(g.filter(ImageFilter.GaussianBlur(r))).astype(np.float32) / 255.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--v-cut", type=float, default=0.795, help="明度阈值：低于它算主体")
    ap.add_argument("--s-cut", type=float, default=0.135, help="饱和度阈值：高于它算主体")
    ap.add_argument("--feather", type=float, default=1.2, help="边缘羽化半径")
    ap.add_argument("--verify", default="", help="给个目录，输出叠在浅底/深底上的验证图")
    args = ap.parse_args()

    im = Image.open(args.src).convert("RGB")
    W, H = im.size
    P = np.asarray(im).astype(np.float32) / 255.0
    print(f"src: {W}x{H}")

    mx, mn = P.max(axis=2), P.min(axis=2)
    V = mx
    S = (mx - mn) / np.maximum(mx, 1e-6)

    v_score = np.clip((args.v_cut - V) / V_BAND, 0, 1)
    s_score = np.clip((S - args.s_cut) / S_BAND, 0, 1)
    alpha = np.maximum(v_score, s_score)
    print(f"V 分位: p05={np.percentile(V,5):.3f} p50={np.percentile(V,50):.3f} p95={np.percentile(V,95):.3f}")
    print(f"S 分位: p05={np.percentile(S,5):.3f} p50={np.percentile(S,50):.3f} p95={np.percentile(S,95):.3f}")
    print(f"初始 alpha: 不透明 {(alpha>0.9).mean()*100:.1f}% / 透明 {(alpha<0.1).mean()*100:.1f}%")

    # ---- 孔洞填充：从四边泛洪，不与边缘连通的低 alpha 区补成 1 ----
    low = 4
    h2, w2 = max(1, H // low), max(1, W // low)
    a_s = np.asarray(Image.fromarray((alpha * 255).astype(np.uint8))
                     .resize((w2, h2), Image.BILINEAR)).astype(np.float32) / 255.0
    bg_s = a_s < 0.5
    reach = np.zeros_like(bg_s)
    reach[0, :] = bg_s[0, :]
    reach[-1, :] = bg_s[-1, :]
    reach[:, 0] = bg_s[:, 0]
    reach[:, -1] = bg_s[:, -1]
    for _ in range(600):
        nb = reach.copy()
        nb[1:, :] |= reach[:-1, :]
        nb[:-1, :] |= reach[1:, :]
        nb[:, 1:] |= reach[:, :-1]
        nb[:, :-1] |= reach[:, 1:]
        new = nb & bg_s
        if new.sum() == reach.sum():
            break
        reach = new
    holes_s = bg_s & ~reach
    holes = np.asarray(Image.fromarray((holes_s * 255).astype(np.uint8))
                       .resize((W, H), Image.BILINEAR)).astype(np.float32) / 255.0
    alpha = np.maximum(alpha, np.clip(holes * 4, 0, 1))
    print(f"内部孔洞 {holes_s.mean()*100:.2f}%")

    # ---- 去孤立噪点 + 羽化 ----
    ai = Image.fromarray((alpha * 255).astype(np.uint8))
    ai = ai.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    if args.feather > 0:
        ai = ai.filter(ImageFilter.GaussianBlur(args.feather))
    alpha = np.asarray(ai).astype(np.float32) / 255.0

    # ---- 反解前景色，去掉边缘残留的浅色背景 ----
    bg = blur(P, 40)
    m3 = np.repeat((alpha > 0.5)[:, :, None], 3, axis=2)
    for _ in range(2):
        bg = blur(np.where(m3, bg, P), 40)

    a3 = alpha[:, :, None]
    a_safe = np.maximum(a3, 0.30)      # 低 alpha 处截断，避免放大噪声
    F = (P - (1 - a3) * bg) / a_safe
    F = np.clip(F, 0, 1)
    F = np.where(a3 < 0.03, 0.0, F)
    F = F * (0.94 + 0.06 * np.clip(alpha, 0, 1))[:, :, None]

    out = np.dstack([(F * 255).astype(np.uint8), (alpha * 255).astype(np.uint8)])
    Image.fromarray(out, "RGBA").save(args.dst, "PNG", optimize=True)
    print(f"saved: {args.dst}")
    print(f"alpha: 透明 {(alpha<0.03).mean()*100:.1f}% / 不透明 {(alpha>0.97).mean()*100:.1f}% "
          f"/ 过渡 {((alpha>=0.03)&(alpha<=0.97)).mean()*100:.1f}%")

    if args.verify:
        import os
        cut = Image.open(args.dst).convert("RGBA")
        for name, col in (("light", (244, 241, 230)), ("dark", (40, 36, 30))):
            bgc = Image.new("RGB", cut.size, col)
            Image.alpha_composite(bgc.convert("RGBA"), cut).convert("RGB") \
                 .resize((620, max(1, int(620 * cut.size[1] / cut.size[0])))) \
                 .save(os.path.join(args.verify, f"verify_{name}.jpg"), quality=93)
        print("verify images written")


if __name__ == "__main__":
    sys.exit(main())
