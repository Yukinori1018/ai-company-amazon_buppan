# -*- coding: utf-8 -*-
"""Amazon物販 全体フロー図を PNG で描画（Mermaid非依存・確実に表示される版）"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib import font_manager as fm

FONT = "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"
fp = fm.FontProperties(fname=FONT)
plt.rcParams["font.family"] = fp.get_name()
fm.fontManager.addfont(FONT)

COL = {
    "start": "#cfeccf",
    "step":  "#dcefff",
    "gate":  "#ffd9d9",
    "rel":   "#fff0c2",
    "dead":  "#e6e6e6",
    "after": "#ecdcf7",
    "health":"#ffe0cc",
}
EDGE = {
    "start": "#3a8c3a",
    "step":  "#2a7fb5",
    "gate":  "#cc3333",
    "rel":   "#d6a400",
    "dead":  "#888888",
    "after": "#8e44ad",
    "health":"#e67e22",
}

fig, ax = plt.subplots(figsize=(11.0, 16.5))
ax.set_xlim(0, 14.6)
ax.set_ylim(0, 21)
ax.axis("off")

boxes = {}  # id -> (cx, cy, w, h)

def box(bid, cx, cy, text, kind="step", w=4.0, h=1.05, fs=12):
    x = cx - w / 2
    y = cy - h / 2
    style = "round,pad=0.02,rounding_size=0.18"
    p = FancyBboxPatch((x, y), w, h, boxstyle=style,
                       linewidth=1.8, edgecolor=EDGE[kind], facecolor=COL[kind])
    ax.add_patch(p)
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs,
            fontproperties=fp, wrap=True)
    boxes[bid] = (cx, cy, w, h)

def arrow(a, b, label=None, side="mid", style="-", color="#444", rad=0.0, lx=None, ly=None):
    ax1, ay1, aw, ah = boxes[a]
    bx1, by1, bw, bh = boxes[b]
    # default: from bottom of a to top of b
    start = (ax1, ay1 - ah/2)
    end = (bx1, by1 + bh/2)
    ls = (0, (4, 3)) if style == "dotted" else "-"
    arr = FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=16,
                          linewidth=1.6, color=color,
                          connectionstyle=f"arc3,rad={rad}", linestyle=ls)
    ax.add_patch(arr)
    if label:
        mx = lx if lx is not None else (start[0] + end[0]) / 2
        my = ly if ly is not None else (start[1] + end[1]) / 2
        ax.text(mx, my, label, ha="center", va="center", fontsize=10,
                fontproperties=fp, color="#b00",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.9))

# --- main spine ---
box("start", 6.0, 20.2, "事業スタート", "start", w=3.0, h=0.8, fs=12)
box("P0", 6.0, 18.7, "0. 事業準備\nアカウント開設・環境整備\n（本人確認 / カード / ツール）", "step")
box("P1", 6.0, 17.0, "1. リサーチ\n売れる商品・仕入れ候補を探す", "step")
box("G1", 6.0, 15.2, "★2. 出品できる商品か？\n出品制限・カテゴリ制限を確認", "gate", h=1.15)
box("P3", 6.0, 13.0, "3. 利益計算\n真の利益・利益率20%以上か判定", "step")
box("G2", 6.0, 11.2, "★4. 仕入れ判断\nGo か NoGo か", "gate")
box("P5", 6.0, 9.6, "5. 仕入れ実行\n発注・入金・領収書PDF取得", "step")
box("P7", 6.0, 8.2, "6. 出品・カタログ登録", "step", h=0.9)
box("P8", 6.0, 6.9, "7. 納品\nFBA倉庫へ納品 or 自己発送準備", "step")
box("P9", 6.0, 5.5, "8. 販売\nカート獲得・価格調整", "step", h=0.9)
box("P10", 6.0, 4.2, "9. 受注〜配送\nFBA=自動 / 自己発送=梱包発送", "step")
box("P11", 6.0, 2.8, "10. 入金・会計\n売上回収・利益確定・記帳", "step")
box("G3", 6.0, 1.2, "★11. 振り返り\nもう一度仕入れる？", "gate", h=0.95)

# --- side boxes ---
box("REL", 10.0, 15.2, "2b. 出品制限の解除\n（必要時のみ・別フロー）\n0円→1点→10点", "rel", w=3.4, h=1.3, fs=11)
box("X1", 2.0, 15.2, "別販路で売る\nor 諦める", "dead", w=2.6, h=1.0, fs=11)

# --- independent parallel flow: after-sales / customer care ---
box("AF", 11.9, 5.6,
    "★12. アフターフォロー\n（独立・並走フロー）\n\n・購入者メッセージ対応(24h以内)\n・返品/返金・返送品の検品\n・注文評価/レビューの確認と対応\n・A-to-Z保証/真贋・知財クレーム",
    "after", w=4.4, h=3.0, fs=10.5)
box("AH", 11.9, 2.6,
    "アカウントヘルス\n(注文不良率ODR等)を健全に保つ\n→悪化でアカウント停止リスク",
    "health", w=4.4, h=1.4, fs=10.5)

# --- main arrows ---
arrow("start", "P0")
arrow("P0", "P1")
arrow("P1", "G1")
arrow("G1", "P3", label="制限なし")
arrow("P3", "G2")
arrow("G2", "P5", label="Go")
arrow("P5", "P7"); arrow("P7", "P8"); arrow("P8", "P9")
arrow("P9", "P10"); arrow("P10", "P11"); arrow("P11", "G3")

# G1 -> REL (right), REL -> P3
relx, rely, relw, relh = boxes["REL"]
g1x, g1y, g1w, g1h = boxes["G1"]
ax.add_patch(FancyArrowPatch((g1x+g1w/2, g1y), (relx-relw/2, rely),
             arrowstyle="-|>", mutation_scale=16, linewidth=1.6, color="#d6a400"))
ax.text((g1x+g1w/2+relx-relw/2)/2, rely+0.35, "要解除", ha="center", fontsize=10,
        fontproperties=fp, color="#b00")
p3x, p3y, p3w, p3h = boxes["P3"]
ax.add_patch(FancyArrowPatch((relx, rely-relh/2), (p3x+p3w/2-0.3, p3y),
             arrowstyle="-|>", mutation_scale=16, linewidth=1.6, color="#d6a400",
             connectionstyle="arc3,rad=-0.3"))

# G1 -> X1 (left, 出品不可), X1 -> P1 (dotted back)
x1x, x1y, x1w, x1h = boxes["X1"]
ax.add_patch(FancyArrowPatch((g1x-g1w/2, g1y), (x1x+x1w/2, x1y),
             arrowstyle="-|>", mutation_scale=16, linewidth=1.6, color="#888"))
ax.text((g1x-g1w/2+x1x+x1w/2)/2, x1y+0.35, "出品不可", ha="center", fontsize=10,
        fontproperties=fp, color="#777")
p1x, p1y, p1w, p1h = boxes["P1"]
ax.add_patch(FancyArrowPatch((x1x, x1y+x1h/2), (p1x-p1w/2, p1y),
             arrowstyle="-|>", mutation_scale=14, linewidth=1.4, color="#888",
             linestyle=(0,(4,3)), connectionstyle="arc3,rad=-0.3"))

# --- loop-back lane on far left: G3 -> up to P1 ---
g3x, g3y, g3w, g3h = boxes["G3"]
lane_x = 0.5
ax.add_patch(FancyArrowPatch((g3x-g3w/2, g3y), (lane_x, g3y),
             arrowstyle="-", linewidth=1.6, color="#2a7fb5"))
ax.add_patch(FancyArrowPatch((lane_x, g3y), (lane_x, p1y),
             arrowstyle="-", linewidth=1.6, color="#2a7fb5"))
ax.add_patch(FancyArrowPatch((lane_x, p1y), (p1x-p1w/2, p1y),
             arrowstyle="-|>", mutation_scale=16, linewidth=1.6, color="#2a7fb5"))
ax.text(lane_x+0.15, (g3y+p1y)/2, "ループ：リサーチに戻る\n（再仕入れ / NoGo / 別商品）",
        ha="left", va="center", fontsize=10, fontproperties=fp, color="#2a7fb5", rotation=90)

# G2 NoGo -> merge into lane
g2x, g2y, g2w, g2h = boxes["G2"]
ax.add_patch(FancyArrowPatch((g2x-g2w/2, g2y), (lane_x, g2y),
             arrowstyle="-", linewidth=1.3, color="#2a7fb5", linestyle=(0,(3,3))))
ax.text(g2x-g2w/2-0.5, g2y+0.3, "NoGo", ha="center", fontsize=10,
        fontproperties=fp, color="#b00")

# --- after-sales arrows ---
p9x, p9y, p9w, p9h = boxes["P9"]
afx, afy, afw, afh = boxes["AF"]
ahx, ahy, ahw, ahh = boxes["AH"]
# 販売〜配送のイベント -> アフターフォロー
ax.add_patch(FancyArrowPatch((p9x+p9w/2, p9y), (afx-afw/2, afy+0.6),
             arrowstyle="-|>", mutation_scale=16, linewidth=1.7, color="#8e44ad"))
ax.text((p9x+p9w/2+afx-afw/2)/2, afy+1.05, "販売後イベント\n（返品・問合せ・評価）",
        ha="center", va="center", fontsize=9.5, fontproperties=fp, color="#8e44ad")
# アフターフォロー -> アカウントヘルス
ax.add_patch(FancyArrowPatch((afx, afy-afh/2), (ahx, ahy+ahh/2),
             arrowstyle="-|>", mutation_scale=16, linewidth=1.7, color="#8e44ad"))
# アカウントヘルス -> 振り返り（指標を反映）
ax.add_patch(FancyArrowPatch((ahx-ahw/2, ahy), (g3x+g3w/2, g3y),
             arrowstyle="-|>", mutation_scale=15, linewidth=1.5, color="#e67e22",
             connectionstyle="arc3,rad=0.15"))
ax.text((ahx-ahw/2+g3x+g3w/2)/2, g3y-0.55, "指標・学びを反映",
        ha="center", va="center", fontsize=9.5, fontproperties=fp, color="#e67e22")

# title
ax.text(7.0, 20.85, "Amazon物販 業務フロー ① 大きな流れ（全体像）",
        ha="center", va="center", fontsize=16, fontproperties=fp, weight="bold")
ax.text(14.4, 0.2, "T-20260529-001 / 秘書カズヨ / 2026-05-29",
        ha="right", fontsize=8, fontproperties=fp, color="#999")

plt.tight_layout()
out = "workspace/output/deliverables/T-20260529-001/01_overview-flow.png"
plt.savefig(out, dpi=140, bbox_inches="tight", facecolor="white")
print("saved", out)
