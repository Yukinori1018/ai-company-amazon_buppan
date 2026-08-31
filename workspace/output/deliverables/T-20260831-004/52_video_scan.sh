#!/usr/bin/env bash
# 52_video_scan.sh — 長尺動画から「特定の文言が映っているフレーム」を探す汎用ハーネス
#
# 使い方:
#   ./52_video_scan.sh <動画パス> <作業ディレクトリ> [開始時刻 HH:MM:SS]
#   その後 53_search.py で作業ディレクトリを検索する。
#
# 設計方針:
#   - 2パス構成。10秒間隔（網羅・時刻が正確）＋ シーン検出（10秒未満の表示を拾う）。
#     どちらか片方では取りこぼす。実測でシーン検出は閾値0.10でもスライドを落とした。
#   - OCR前にスライド領域だけを切り出す。Zoomの参加者パネル（上部）とDock（下部）が
#     ノイズになり、キーワード検索の誤ヒットを量産するため。CROP は動画ごとに要調整。
#   - OCRは 51_ocr.swift（macOS Vision）。1プロセスに多数のファイルを渡して並列化する。
set -euo pipefail

VIDEO="${1:?動画パスを指定してください}"
WORK="${2:?作業ディレクトリを指定してください}"
START_CLOCK="${3:-00:00:00}"   # 録画開始の実時刻。フレーム番号→実時刻の換算に使う

# 切り出し範囲 w:h:x:y。ffplay等で1枚抜いて目視で決めること（既定値は2590x1558のZoom画面用）
CROP="${CROP:-2360:1330:230:175}"
INTERVAL="${INTERVAL:-10}"     # 秒
SCENE_TH="${SCENE_TH:-0.10}"

BIN="$(cd "$(dirname "$0")" && pwd)/ocr"
[ -x "$BIN" ] || { echo "先に: swiftc -O -o $BIN $(dirname "$0")/51_ocr.swift" >&2; exit 1; }

mkdir -p "$WORK/frames" "$WORK/scene"
echo "[1/3] ${INTERVAL}秒間隔で抽出"
ffmpeg -v error -i "$VIDEO" -vf "fps=1/${INTERVAL},crop=${CROP}" -q:v 4 \
       -start_number 0 "$WORK/frames/f_%05d.jpg" -y

echo "[2/3] シーン検出で抽出（10秒未満の表示の取りこぼし対策）"
# 画面が終始静止している素材では該当0枚になり ffmpeg が異常終了する。パス1だけで続行してよい。
ffmpeg -v error -i "$VIDEO" -vf "select='gt(scene,${SCENE_TH})',crop=${CROP}" \
       -vsync vfr -q:v 4 "$WORK/scene/s_%05d.jpg" -y || echo "  （シーン変化なし。パス1のみで続行します）"

echo "[3/3] OCR（4並列）"
ocr_dir() {
  local dir="$1" out="$2"
  if ! ls "$dir"/*.jpg >/dev/null 2>&1; then : > "$out"; return; fi
  ls "$dir"/*.jpg | sort > "$dir/list.txt"
  split -l "$(( ($(wc -l < "$dir/list.txt") / 4) + 1 ))" "$dir/list.txt" "$dir/p_"
  for p in "$dir"/p_??; do ( xargs "$BIN" < "$p" > "$p.tsv" 2>/dev/null ) & done
  wait
  cat "$dir"/p_??.tsv | sort > "$out"
  rm -f "$dir"/p_?? "$dir"/p_??.tsv "$dir/list.txt"
}
ocr_dir "$WORK/frames" "$WORK/frames.tsv"
ocr_dir "$WORK/scene"  "$WORK/scene.tsv"

echo "$INTERVAL" > "$WORK/interval.txt"
echo "$START_CLOCK" > "$WORK/start_clock.txt"
echo "完了: $WORK/frames.tsv ($(wc -l < "$WORK/frames.tsv" | tr -d ' ')件) / $WORK/scene.tsv ($(wc -l < "$WORK/scene.tsv" | tr -d ' ')件)"
