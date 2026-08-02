# -*- coding: utf-8 -*-
"""フロー図描画の共通ヘルパー（matplotlib + IPAGothic）"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib import font_manager as fm

import os as _os

# OS 横断でゴシック系日本語フォントを自動選択（macOS=ヒラギノ W3 / Linux=IPAGothic）
_FONT_CANDIDATES = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",          # macOS（最優先・上品）
    _os.path.expanduser("~/Library/Fonts/GenShinGothic-Heavy.ttf"),  # macOS 代替
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",        # Linux（IPAGothic）
    "/Library/Fonts/Arial Unicode.ttf",                          # 最終フォールバック
]
FONT = next((c for c in _FONT_CANDIDATES if _os.path.exists(c)), None)
if FONT is None:
    raise FileNotFoundError("日本語フォントが見つかりません: " + ", ".join(_FONT_CANDIDATES))
FP = fm.FontProperties(fname=FONT)
fm.fontManager.addfont(FONT)
plt.rcParams["font.family"] = FP.get_name()

COL = {"start":"#cfeccf","step":"#dcefff","gate":"#ffd9d9","rel":"#fff0c2",
       "dead":"#e6e6e6","after":"#ecdcf7","health":"#ffe0cc","info":"#d9f2ec"}
EDGE = {"start":"#3a8c3a","step":"#2a7fb5","gate":"#cc3333","rel":"#d6a400",
        "dead":"#888888","after":"#8e44ad","health":"#e67e22","info":"#16a085"}

class Flow:
    def __init__(self, w, h, xlim, ylim, title=None):
        self.fig, self.ax = plt.subplots(figsize=(w, h))
        self.ax.set_xlim(*xlim); self.ax.set_ylim(*ylim); self.ax.axis("off")
        self.boxes = {}
        if title:
            self.ax.text((xlim[0]+xlim[1])/2, ylim[1]-0.4, title, ha="center",
                         va="center", fontsize=16, fontproperties=FP, weight="bold")

    def box(self, bid, cx, cy, text, kind="step", w=4.0, h=1.05, fs=11):
        x, y = cx-w/2, cy-h/2
        p = FancyBboxPatch((x,y), w, h, boxstyle="round,pad=0.02,rounding_size=0.16",
                           linewidth=1.7, edgecolor=EDGE[kind], facecolor=COL[kind])
        self.ax.add_patch(p)
        self.ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, fontproperties=FP)
        self.boxes[bid] = (cx, cy, w, h)

    def _anchor(self, bid, side):
        cx, cy, w, h = self.boxes[bid]
        return {"top":(cx,cy+h/2),"bottom":(cx,cy-h/2),
                "left":(cx-w/2,cy),"right":(cx+w/2,cy),"center":(cx,cy)}[side]

    def arrow(self, a, b, fa="bottom", tb="top", label=None, color="#444",
              style="-", rad=0.0, lx=None, ly=None, lc="#b00", fs=9.5):
        s = self._anchor(a, fa); e = self._anchor(b, tb)
        ls = (0,(4,3)) if style=="dotted" else "-"
        self.ax.add_patch(FancyArrowPatch(s, e, arrowstyle="-|>", mutation_scale=15,
                          linewidth=1.6, color=color, linestyle=ls,
                          connectionstyle=f"arc3,rad={rad}"))
        if label:
            mx = lx if lx is not None else (s[0]+e[0])/2
            my = ly if ly is not None else (s[1]+e[1])/2
            self.ax.text(mx, my, label, ha="center", va="center", fontsize=fs,
                         fontproperties=FP, color=lc,
                         bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.92))

    def note(self, x, y, text, color="#777", fs=9.5, ha="center"):
        self.ax.text(x, y, text, ha=ha, va="center", fontsize=fs, fontproperties=FP, color=color)

    def save(self, path, dpi=140):
        plt.tight_layout()
        self.fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
        print("saved", path)
