#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""prepare_ai.py —— AI 生图入片前的三步处理：去平台水印 + 尺寸校准 + 转 JPG。

用法：
    python prepare_ai.py <input.png> <output.jpg> [--w 1920 --h 1080] [--no-dewatermark]

为什么需要：
 1. 生图工具默认在右下角硬嵌平台水印（形如「AI生成 / 品牌名」），footnote 参数未必关得掉，
    直接入片会穿帮。
 2. 模型常输出 1920x1072 这类"接近但不是"的尺寸，必须精确裁到目标分辨率。
 3. 抠图请另用 cutout_bg.py（本脚本处理不透明的普通素材）。

去水印做法：
    取同 x 位置上方 120px 的同源纹理平移覆盖 + 逐通道亮度匹配 + 只在左/上两边羽化
    （右/下贴画面边界，必须完全替换，不能羽化）。
"""
import argparse
import sys

import numpy as np
from PIL import Image, ImageOps

# 水印框在 1920x1080 坐标系下（略放宽，确保盖住主标与下方小字）
WM_BOX = (1760, 985, 1920, 1080)
WM_DY = -120
WM_FEATHER = 26


def cover(arr, box, dx=0, dy=0, feather=26, left_top_only=True):
    """用 (dx,dy) 平移后的同源纹理羽化覆盖 box 区域。"""
    x0, y0, x1, y1 = box
    h, w = y1 - y0, x1 - x0
    src = arr[y0 + dy:y1 + dy, x0 + dx:x1 + dx].copy()
    tgt = arr[y0:y1, x0:x1].copy()
    if src.shape != tgt.shape:
        raise ValueError(f"source shape {src.shape} != target {tgt.shape}, box={box}")

    ref = arr[y0 - 10:y0, x0:x1].mean(axis=(0, 1))
    sref = src[-10:, :, :].mean(axis=(0, 1)) if left_top_only else src[:10, :, :].mean(axis=(0, 1))
    src = np.clip(src + (ref - sref), 0, 255)

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.minimum(xx, yy) if left_top_only else np.minimum.reduce([xx, w - 1 - xx, yy, h - 1 - yy])
    alpha = np.clip(d / float(feather), 0.0, 1.0)[..., None]
    arr[y0:y1, x0:x1] = tgt * (1 - alpha) + src * alpha


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--w", type=int, default=1920)
    ap.add_argument("--h", type=int, default=1080)
    ap.add_argument("--no-dewatermark", action="store_true")
    ap.add_argument("--quality", type=int, default=93)
    args = ap.parse_args()

    im = Image.open(args.src).convert("RGB")
    print(f"src: {im.size}")

    if im.size != (args.w, args.h):
        im = ImageOps.fit(im, (args.w, args.h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        print(f"fit -> {im.size}")

    if not args.no_dewatermark:
        arr = np.asarray(im).astype(np.float32)
        # 按实际尺寸等比缩放水印框，兼容非 1920x1080
        sx, sy = args.w / 1920.0, args.h / 1080.0
        box = (int(WM_BOX[0] * sx), int(WM_BOX[1] * sy), args.w, args.h)
        cover(arr, box, dx=0, dy=int(WM_DY * sy), feather=WM_FEATHER, left_top_only=True)
        im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        print("watermark covered")

    im.save(args.dst, "JPEG", quality=args.quality, subsampling=0, optimize=True)
    import os
    print(f"saved: {args.dst}  {os.path.getsize(args.dst)} B")


if __name__ == "__main__":
    sys.exit(main())
