#!/bin/bash
# render_segmented.sh —— 分段渲染 + 帧数先验 + 正确的 ffprobe 校验
#
# 用法：bash render_segmented.sh <总帧数> [每段帧数]
#   例：bash render_segmented.sh 7893 1316
#
# 设计要点（见 references/rendering.md）：
#  1. 每段 <=1300 帧，崩了只重跑 1/N
#  2. .frames 先验文件记录实际帧数，重跑时比对，不靠 .done 一个标记
#  3. 帧数校验用 bash 直调 ffprobe —— Node 的 execSync 不认 /c/ 这种 MSYS 路径
#  4. 全部成功才 concat，避免半成品合片
set -euo pipefail
cd "$(dirname "$0")/.."

CLI="node node_modules/@remotion/cli/remotion-cli.js"
ENTRY="${ENTRY:-remotion/entry.jsx}"
COMP="${COMP:-Main}"
OUT="$(pwd)/out"
AUDIO="${AUDIO:-}"          # 可选：原曲路径，给了才混音
FINAL="${FINAL:-$OUT/full.mp4}"
CONCURRENCY="${CONCURRENCY:-1}"

TOTAL="${1:?用法: render_segmented.sh <总帧数> [每段帧数]}"
PER="${2:-1316}"
mkdir -p "$OUT"

# 生成段边界
segments=()
s=0
while [ "$s" -lt "$TOTAL" ]; do
  e=$((s + PER - 1))
  [ "$e" -ge "$TOTAL" ] && e=$((TOTAL - 1))
  segments+=("$s-$e")
  s=$((e + 1))
done

echo "总计 $TOTAL 帧，拆成 ${#segments[@]} 段（每段 ≤$PER 帧），并发 $CONCURRENCY"

check_frames() { # <文件> <期望帧数>
  local f="$1" want="$2" nb
  nb=$(ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames \
        -of csv=p=0 "$f" 2>/dev/null | tr -d ' ,')
  [ "$nb" = "$want" ]
}

for i in "${!segments[@]}"; do
  idx=$((i + 1))
  range="${segments[$i]}"
  from="${range%-*}"; to="${range#*-}"
  want=$((to - from + 1))
  file="$OUT/seg$idx.mp4"
  stamp="$OUT/seg$idx.frames"

  # 先验：文件存在 + 帧数正确才跳过
  if [ -f "$file" ] && [ -f "$stamp" ] && [ "$(cat "$stamp")" = "$want" ] && check_frames "$file" "$want"; then
    echo "seg$idx ($range) 已完成，跳过"
    continue
  fi

  echo "=== seg$idx  frames $from-$to  ($want 帧)  $(date +%H:%M:%S) ==="
  $CLI render "$ENTRY" "$COMP" "$file" \
    --frames="$from-$to" \
    --concurrency="$CONCURRENCY" \
    --timeout=180000 \
    --log=error 2>&1 | tail -3

  if ! check_frames "$file" "$want"; then
    echo "!! seg$idx FRAME MISMATCH: 期望 $want，实际 $(ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames -of csv=p=0 "$file" 2>/dev/null | tr -d ' ,')"
    echo "   先检查是否有僵尸 ffmpeg/chrome 进程占内存，再重跑本段。"
    exit 1
  fi
  echo "$want" > "$stamp"
  echo "seg$idx OK ($want 帧)  $(date +%H:%M:%S)"
done

# ---- 合片 ----
echo "=== concat $(date +%H:%M:%S) ==="
inputs=()
for i in "${!segments[@]}"; do inputs+=(-i "$OUT/seg$((i + 1)).mp4"); done
n="${#segments[@]}"
streams=""
for ((k = 0; k < n; k++)); do streams+="[$k:v]"; done

if [ -n "$AUDIO" ]; then
  ffmpeg -y -hide_banner -loglevel error \
    "${inputs[@]}" -i "$AUDIO" \
    -filter_complex "${streams}concat=n=$n:v=1:a=0[v];[$n:a]aresample=48000[a]" \
    -map "[v]" -map "[a]" \
    -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p \
    -c:a aac -b:a 256k -ar 48000 -shortest \
    "$FINAL"
else
  ffmpeg -y -hide_banner -loglevel error \
    "${inputs[@]}" \
    -filter_complex "${streams}concat=n=$n:v=1:a=0[v]" \
    -map "[v]" -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p \
    "$FINAL"
fi

nb=$(ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames -of csv=p=0 "$FINAL" | tr -d ' ,')
echo "合片完成：$FINAL  ($nb 帧 / 期望 $TOTAL)"
[ "$nb" = "$TOTAL" ] || { echo "!! 合片帧数不符，检查各段是否齐全"; exit 1; }
echo "ALL_DONE $(date +%H:%M:%S)"
