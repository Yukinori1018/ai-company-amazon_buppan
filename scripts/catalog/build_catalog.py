#!/usr/bin/env python3
"""
build_catalog.py — 成果物カタログを deliverables/ の実体から機械生成する。

これは何か（1行）:
    `workspace/output/deliverables/` を走査し、マスター CSV と HTML 版カタログを
    再生成する。手で1行ずつ追記する運用（積み残し 248 件）を廃止するためのもの。

設計の柱（T-20260909-003 / 2026-09-09）:
  1. **真実はファイルシステム**。git 追跡の有無ではない。
     追跡していない成果物（NETSEA 卸値を含む行データ等）も、社長のローカルには
     実在してクリックで開ける。カタログから消してはいけない。
     → 各行に `公開状態` を持たせ、「GitHub公開」/「ローカルのみ」を明示する。
  2. **人が書いた文章は絶対に消さない**。既存 CSV の
     内容（要約）/ 暫定結果 / 備考 / 種別 / 担当 / ToDo・タスク名 / 社長レビュー は
     リポジトリ相対パスをキーに引き継ぐ。新規行の要約は「要記入」で出す。
  3. **タイトルにファイル名の付番を必ず含める**（`03_` `A3_` `B1L_` など）。
     社長が「03 の資料」と言えるようにするため。
  4. **冪等**。同じ入力なら同じ出力。再実行しても差分は増えない。

使い方:
    python3 scripts/catalog/build_catalog.py              # CSV と HTML を再生成
    python3 scripts/catalog/build_catalog.py --dry-run    # 書かずに件数だけ出す
    python3 scripts/catalog/build_catalog.py --check-untracked   # 追跡漏れの検知
    python3 scripts/catalog/build_catalog.py --warn-untracked-for-commit
        （pre-commit から呼ばれる。今回の commit が触ったフォルダだけを見る）

出力:
    workspace/output/deliverables/T-20260601-001/deliverables-catalog.csv  … マスター
    workspace/output/deliverables/T-20260601-001/00_成果物カタログ.html     … 社長の入口

Google スプレッドシートへの反映は `sync_catalog_to_sheet.py` が別途行う。
このスクリプトは外部へ一切送信しない。
"""

from __future__ import annotations

import argparse
import csv
import html as html_mod
import os
import re
import subprocess
import sys
from datetime import date, datetime

# ── パス定数 ────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
DELIVERABLES = os.path.join("workspace", "output", "deliverables")
CATALOG_DIR = os.path.join(DELIVERABLES, "T-20260601-001")
CSV_PATH = os.path.join(CATALOG_DIR, "deliverables-catalog.csv")
HTML_PATH = os.path.join(CATALOG_DIR, "00_成果物カタログ.html")

# 社長の Finder 側の入口（deliverables へのシンボリックリンク）。
# 環境変数で差し替え可能にしてある（クラウドセッションでは別パスになるため）。
LOCAL_BASE = os.environ.get(
    "CATALOG_LOCAL_BASE",
    os.path.expanduser("~/Documents/AI Company Outputs/Amazon物販事業"),
)

COLUMNS = [
    "チケットID",
    "ToDo/タスク名",
    "成果物タイトル",
    "内容（要約）",
    "暫定結果",
    "種別",
    "公開状態",
    "ローカルリンク",
    "GitHubリンク",
    "リポジトリ相対パス",
    "担当",
    "形式",
    "作成日",
    "社長レビュー",
    "備考",
]

NEEDS_INPUT = "要記入"

# ── 走査対象の絞り込み ──────────────────────────────────────────────────────
# 成果物ではないもの（作業の残骸・キャッシュ・生データ）はカタログに載せない。
# ここを緩めると 1,388 ファイルが並んで一覧の意味が消える。
EXCLUDE_DIR_NAMES = {
    ".git", ".pytest_cache", "__pycache__", "node_modules", ".ipynb_checkpoints",
    "raw", "raw_offers", "state", "out", ".venv", "venv",
}
# 本人特定情報（住所・電話）を含むため CLAUDE.md §6 で Git 除外しているフォルダ。
# カタログ（PUBLIC リポに載る CSV）にはファイル名も出さない。
EXCLUDE_DIR_PATHS = {
    os.path.join(DELIVERABLES, "T-20260817-006", "公開用"),
    os.path.join(DELIVERABLES, "T-20260817-006", "会社概要_配布用"),
}
EXCLUDE_EXT = {
    ".gz", ".log", ".pid", ".bak", ".tmp", ".lock", ".pyc", ".tag",
    ".jsonl", ".old-packbug", ".until-20260831", ".round1-oldcosts",
}
EXCLUDE_NAMES = {
    ".DS_Store", ".gitignore", "STOP", "FINISHED", "CACHEDIR.TAG",
    "seen_asins.txt", "heartbeat.json", "shard_cursors.json", ".env",
}
EXCLUDE_NAME_RE = re.compile(r"(_cache\.json$|\.csv\.tmp$|^\.)")

# 拡張子 → 種別の既定値（人が種別を書いていない新規行の初期値）
KIND_BY_EXT = {
    ".md": "レポート", ".html": "レポート", ".htm": "レポート",
    ".csv": "データ", ".json": "データ", ".xlsx": "データ",
    ".py": "スクリプト", ".sh": "スクリプト", ".js": "スクリプト",
    ".png": "図", ".jpg": "図", ".svg": "図",
    ".pdf": "資料", ".pptx": "スライド", ".plist": "設定ファイル",
    ".css": "スクリプト", ".xml": "データ", ".txt": "資料", ".swift": "スクリプト",
}

# 付番の接頭辞。`01_` `03b_` `A3_` `B1L_` `C1_` を拾う。
NUMBER_PREFIX_RE = re.compile(r"^([0-9]{1,3}[A-Za-z]?|[A-Z][0-9]{0,2}[A-Z]?)_")


# ── 小さなユーティリティ ────────────────────────────────────────────────────
def run_git(args: list[str]) -> str:
    """git を叩いて標準出力を返す。失敗したら空文字（fail-open）。"""
    try:
        out = subprocess.run(
            ["git", "-c", "core.quotePath=false"] + args,
            cwd=REPO_ROOT, capture_output=True, text=True, check=False,
        )
        return out.stdout
    except Exception:
        return ""


def tracked_paths() -> set[str]:
    """git 追跡下にあるファイルの相対パス集合。"""
    out = run_git(["ls-files", DELIVERABLES])
    return {line for line in out.splitlines() if line}


def current_branch() -> str:
    return (run_git(["rev-parse", "--abbrev-ref", "HEAD"]).strip() or "main")


def natural_key(name: str):
    """`01_` `02_` `10_` を人間の期待どおりに並べる。数字は数値として比較する。"""
    parts = re.split(r"(\d+)", name)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def number_prefix(stem: str) -> str:
    m = NUMBER_PREFIX_RE.match(stem)
    return m.group(1) if m else ""


def make_title(filename: str, curated: str) -> str:
    """
    タイトルに付番を必ず含める。
    人が書いたタイトル（curated）があればそれを活かし、頭に付番を付け直す。
    無ければファイル名から作る。
    """
    stem = os.path.splitext(filename)[0]
    prefix = number_prefix(stem)
    base = curated.strip() if curated else stem[len(prefix) + 1:].replace("_", " ")
    if not base:
        base = stem
    if prefix and not base.startswith(prefix + "_") and not base.startswith(prefix + " "):
        return f"{prefix}_{base}"
    return base


def file_date(abs_path: str) -> str:
    try:
        return datetime.fromtimestamp(os.path.getmtime(abs_path)).strftime("%Y-%m-%d")
    except OSError:
        return ""


# ── 走査 ────────────────────────────────────────────────────────────────────
def scan_files() -> list[str]:
    """カタログに載せる候補ファイルを、リポジトリ相対パスで返す。"""
    found: list[str] = []
    root_abs = os.path.join(REPO_ROOT, DELIVERABLES)
    for dirpath, dirnames, filenames in os.walk(root_abs):
        rel_dir = os.path.relpath(dirpath, REPO_ROOT)
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDE_DIR_NAMES
            and os.path.join(rel_dir, d) not in EXCLUDE_DIR_PATHS
        ]
        dirnames.sort(key=natural_key)
        for fn in sorted(filenames, key=natural_key):
            ext = os.path.splitext(fn)[1].lower()
            if fn in EXCLUDE_NAMES or ext in EXCLUDE_EXT or EXCLUDE_NAME_RE.search(fn):
                continue
            rel = os.path.join(rel_dir, fn)
            # カタログ自身は載せない（自己参照で毎回1行増えて冪等でなくなる）。
            if rel in (HTML_PATH, CSV_PATH):
                continue
            found.append(rel)
    return found


def ticket_of(rel_path: str) -> str:
    """`workspace/output/deliverables/T-XXXX/...` から チケットID を取る。"""
    parts = rel_path.split(os.sep)
    return parts[3] if len(parts) > 3 else ""


def subpath_of(rel_path: str) -> str:
    """チケットフォルダ配下の相対パス（サブフォルダを含む）。"""
    parts = rel_path.split(os.sep)
    return os.path.join(*parts[4:]) if len(parts) > 4 else os.path.basename(rel_path)


# ── 既存 CSV の引き継ぎ ─────────────────────────────────────────────────────
CARRY_COLUMNS = [
    "ToDo/タスク名", "内容（要約）", "暫定結果", "種別", "担当",
    "社長レビュー", "備考", "作成日", "成果物タイトル",
]


def load_existing(csv_path: str) -> tuple[dict[str, dict], list[dict]]:
    """
    既存 CSV を読む。BOM 付きヘッダに耐える。

    戻り値は (パス→行 の索引, 全行のリスト)。
    フォルダ単位の行は同じパスを複数行が共有している（例: T-20260705-001/ が3行）。
    索引だけにすると人が書いた文章を落とすので、全行も返して両方使う。
    """
    if not os.path.exists(csv_path):
        return {}, []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    idx: dict[str, dict] = {}
    for r in rows:
        key = (r.get("リポジトリ相対パス") or "").strip()
        if key:
            idx.setdefault(key, r)          # 重複パスは先着（人が書いた最初の行）を採る
    return idx, rows


def carried(existing: dict, col: str) -> str:
    return (existing.get(col) or "").strip() if existing else ""


# ── 行の組み立て ────────────────────────────────────────────────────────────
def ticket_level_carry(existing: dict[str, dict]) -> dict[str, dict]:
    """
    チケット単位で共有できる欄（ToDo・タスク名／暫定結果）を、既存 CSV から拾っておく。
    これが無いと、新しく載る 500 行超のファイルが「どのタスクの成果物か」を失う。
    """
    out: dict[str, dict] = {}
    for path, row in existing.items():
        t = ticket_of(path)
        if not t:
            continue
        slot = out.setdefault(t, {"ToDo/タスク名": "", "暫定結果": ""})
        for col in ("ToDo/タスク名", "暫定結果"):
            if not slot[col] and (row.get(col) or "").strip():
                slot[col] = row[col].strip()
    return out


def build_rows(files: list[str], existing: dict[str, dict], all_existing: list[dict],
               tracked: set[str], branch: str) -> list[dict]:
    rows = []
    by_ticket = ticket_level_carry(existing)

    # 既存 CSV がフォルダ単位で1行にしていたもの（`.../code/` 等）は、その形のまま残す。
    # 中のファイルも別行として並ぶが、人が書いた説明を失わないことを優先する。
    dir_rows = [r for r in all_existing
                if (r.get("リポジトリ相対パス") or "").strip().endswith("/")
                and os.path.isdir(os.path.join(
                    REPO_ROOT, r["リポジトリ相対パス"].strip().rstrip("/")))]
    for prev in sorted(dir_rows, key=lambda r: natural_key(r["リポジトリ相対パス"])):
        rel = prev["リポジトリ相対パス"].strip()
        ticket = ticket_of(rel.rstrip("/") + "/x")
        sub = subpath_of(rel.rstrip("/") + "/x")
        sub = os.path.dirname(sub)
        rows.append({
            "チケットID": ticket,
            "ToDo/タスク名": carried(prev, "ToDo/タスク名"),
            "成果物タイトル": carried(prev, "成果物タイトル") or rel,
            "内容（要約）": carried(prev, "内容（要約）") or NEEDS_INPUT,
            "暫定結果": carried(prev, "暫定結果"),
            "種別": carried(prev, "種別") or "フォルダ",
            "公開状態": "フォルダ",
            "ローカルリンク": f"{LOCAL_BASE}/{ticket}/{sub}".rstrip("/").replace(os.sep, "/"),
            "GitHubリンク": carried(prev, "GitHubリンク"),
            "リポジトリ相対パス": rel,
            "担当": carried(prev, "担当"),
            "形式": carried(prev, "形式") or "フォルダ",
            "作成日": carried(prev, "作成日"),
            "社長レビュー": carried(prev, "社長レビュー") or "未",
            "備考": carried(prev, "備考"),
        })

    # deliverables の外を指す既存行（docs/reference/… 等）も、実在するなら残す。
    for prev in all_existing:
        rel = (prev.get("リポジトリ相対パス") or "").strip()
        if not rel or rel.startswith(DELIVERABLES.replace(os.sep, "/")) or rel.endswith("/"):
            continue
        if not os.path.exists(os.path.join(REPO_ROOT, rel)):
            continue
        row = {c: (prev.get(c) or "").strip() for c in COLUMNS}
        row["リポジトリ相対パス"] = rel
        row["チケットID"] = prev.get("チケットID") or prev.get("﻿チケットID") or ""
        row["公開状態"] = "GitHub公開" if rel in tracked else "ローカルのみ"
        row["ローカルリンク"] = row["ローカルリンク"] or ""
        row["内容（要約）"] = row["内容（要約）"] or NEEDS_INPUT
        rows.append(row)

    for rel in files:
        prev = existing.get(rel, {})
        fn = os.path.basename(rel)
        ext = os.path.splitext(fn)[1].lower()
        ticket = ticket_of(rel)
        is_tracked = rel in tracked
        sub = subpath_of(rel)

        fallback = by_ticket.get(ticket, {})
        rows.append({
            "チケットID": ticket,
            "ToDo/タスク名": carried(prev, "ToDo/タスク名") or fallback.get("ToDo/タスク名", ""),
            "成果物タイトル": make_title(fn, carried(prev, "成果物タイトル")),
            "内容（要約）": carried(prev, "内容（要約）") or NEEDS_INPUT,
            "暫定結果": carried(prev, "暫定結果") or fallback.get("暫定結果", ""),
            "種別": carried(prev, "種別") or KIND_BY_EXT.get(ext, "その他"),
            "公開状態": "GitHub公開" if is_tracked else "ローカルのみ",
            "ローカルリンク": f"{LOCAL_BASE}/{ticket}/{sub}".replace(os.sep, "/"),
            "GitHubリンク": (
                "https://github.com/Yukinori1018/ai-company-amazon_buppan/blob/"
                f"{branch}/{rel}".replace(os.sep, "/") if is_tracked else ""
            ),
            "リポジトリ相対パス": rel.replace(os.sep, "/"),
            "担当": carried(prev, "担当"),
            "形式": ext.lstrip(".") or "-",
            "作成日": carried(prev, "作成日") or file_date(os.path.join(REPO_ROOT, rel)),
            "社長レビュー": carried(prev, "社長レビュー") or "未",
            "備考": carried(prev, "備考"),
        })

    # チケットIDの新しい順（＝社長が直近の仕事を上で見られる）。
    # フォルダ内は付番順。
    rows.sort(key=lambda r: (
        [-ord(c) for c in r["チケットID"]],     # 文字列の降順を安定に作る
        natural_key(r["リポジトリ相対パス"]),
    ))
    rows.sort(key=lambda r: r["チケットID"], reverse=True)
    return rows


# ── CSV 出力 ────────────────────────────────────────────────────────────────
def write_csv(path: str, rows: list[dict]) -> bool:
    """書き込む。内容が同じなら触らない（＝冪等・自動同期を無駄に走らせない）。"""
    from io import StringIO
    buf = StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in COLUMNS})
    new = "﻿" + buf.getvalue()          # Excel 対策の BOM は従来どおり付ける
    old = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = f.read()
    if old == new:
        return False
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    return True


# ── HTML 出力（社長の入口）──────────────────────────────────────────────────
HTML_HEAD = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>成果物カタログ — Amazon物販事業</title>
<style>
:root{color-scheme:light dark;
 --bg:#fff;--surface:#f5f7f9;--text:#1b1f24;--muted:#59626d;--border:#d5dae1;
 --accent:#1c5b86;--accent-bg:#eef5fa;--warn:#8a4b00;--warn-bg:#fdf1df;--ok:#1b6144;--ok-bg:#eaf4ef;}
@media (prefers-color-scheme:dark){:root{
 --bg:#15181c;--surface:#1d2126;--text:#e4e8ec;--muted:#aab4bf;--border:#333a43;
 --accent:#79b4dc;--accent-bg:#1a2a36;--warn:#f0b866;--warn-bg:#332616;--ok:#84cfa9;--ok-bg:#17281f;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-size:15px;line-height:1.7;
 font-family:"Hiragino Sans","Yu Gothic Medium","Noto Sans JP",system-ui,sans-serif;}
.wrap{max-width:1080px;margin:0 auto;padding:28px 18px 80px;}
h1{font-size:23px;margin:0 0 6px;}
.lead{margin:0 0 18px;color:var(--muted);font-size:14px;}
.bar{position:sticky;top:0;background:var(--bg);padding:12px 0;border-bottom:1px solid var(--border);z-index:5;}
input[type=search]{width:100%;padding:10px 12px;font-size:15px;border:1px solid var(--border);
 border-radius:8px;background:var(--surface);color:var(--text);}
.chips{margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;}
.chip{font-size:12.5px;padding:4px 10px;border:1px solid var(--border);border-radius:999px;
 background:var(--surface);color:var(--muted);cursor:pointer;}
.chip[aria-pressed=true]{background:var(--accent-bg);color:var(--accent);border-color:var(--accent);}
.count{margin:12px 0 4px;font-size:13px;color:var(--muted);}
.tk{margin:22px 0 0;border:1px solid var(--border);border-radius:10px;overflow:hidden;}
.tk>h2{margin:0;padding:10px 14px;background:var(--surface);font-size:14.5px;
 border-bottom:1px solid var(--border);display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;}
.tk>h2 .task{font-weight:400;color:var(--muted);font-size:13px;}
.row{padding:10px 14px;border-bottom:1px solid var(--border);}
.row:last-child{border-bottom:0;}
.row a.t{color:var(--accent);text-decoration:none;font-weight:600;}
.row a.t:hover{text-decoration:underline;}
.meta{margin-top:3px;font-size:12.5px;color:var(--muted);display:flex;flex-wrap:wrap;gap:8px;}
.tag{padding:1px 7px;border:1px solid var(--border);border-radius:4px;}
.pub-local{background:var(--warn-bg);color:var(--warn);border-color:transparent;}
.pub-gh{background:var(--ok-bg);color:var(--ok);border-color:transparent;}
.todo{background:var(--warn-bg);color:var(--warn);border-color:transparent;}
details.sum{margin-top:4px;font-size:13.5px;color:var(--muted);}
details.sum summary{cursor:pointer;color:var(--accent);}
.note{margin-top:26px;padding:12px 14px;background:var(--surface);border-radius:8px;
 font-size:13px;color:var(--muted);}
</style>
</head>
<body><div class="wrap">
"""

HTML_TAIL = """
<div class="note">
<p>リンクはローカルのファイルを直接開きます（<code>file://</code>）。ブラウザで表示されない形式（CSV・xlsx など）はダウンロードされます。</p>
<p><b>公開状態</b>：「GitHub公開」はリポジトリに載っているもの。「ローカルのみ」は NETSEA の卸値など公開できないデータを含むため Git 追跡していないものです。どちらもこのカタログから開けます。</p>
<p>このページは <code>python3 scripts/catalog/build_catalog.py</code> で再生成します。要約が「要記入」の行は、まだ人の手が入っていません。</p>
</div>
</div>
<script>
(function(){
  var q=document.getElementById('q'), rows=[].slice.call(document.querySelectorAll('.row'));
  var chips=[].slice.call(document.querySelectorAll('.chip')), out=document.getElementById('count');
  var active='';
  function apply(){
    var t=q.value.trim().toLowerCase(), n=0;
    rows.forEach(function(r){
      var hay=r.dataset.k;
      var ok=(!t||hay.indexOf(t)>=0)&&(!active||r.dataset.kind===active);
      r.style.display=ok?'':'none'; if(ok)n++;
    });
    document.querySelectorAll('.tk').forEach(function(g){
      var any=[].slice.call(g.querySelectorAll('.row')).some(function(r){return r.style.display!=='none';});
      g.style.display=any?'':'none';
    });
    out.textContent=n+' 件を表示';
  }
  q.addEventListener('input',apply);
  chips.forEach(function(c){c.addEventListener('click',function(){
    var v=c.dataset.kind;
    active=(active===v)?'':v;
    chips.forEach(function(x){x.setAttribute('aria-pressed',String(x.dataset.kind===active));});
    apply();
  });});
  apply();
})();
</script>
</body></html>
"""


def esc(s: str) -> str:
    return html_mod.escape(s or "", quote=True)


def write_html(path: str, rows: list[dict]) -> bool:
    from collections import Counter, OrderedDict
    groups: "OrderedDict[str, list[dict]]" = OrderedDict()
    for r in rows:
        groups.setdefault(r["チケットID"], []).append(r)

    kinds = [k for k, _ in Counter(r["種別"] for r in rows).most_common(12)]
    todo_n = sum(1 for r in rows if r["内容（要約）"] == NEEDS_INPUT)

    parts = [HTML_HEAD]
    parts.append(f"<h1>成果物カタログ</h1>")
    parts.append(
        f'<p class="lead">Amazon物販事業／全 {len(rows)} 件・{len(groups)} チケット。'
        f'生成 {date.today():%Y-%m-%d}。要約が未記入のものが {todo_n} 件あります。</p>'
    )
    parts.append('<div class="bar">')
    parts.append('<input type="search" id="q" placeholder="チケットID・タイトル・要約で絞り込む（例: T-20260904 / 発注セット）">')
    parts.append('<div class="chips">')
    for k in kinds:
        parts.append(f'<button class="chip" data-kind="{esc(k)}" aria-pressed="false">{esc(k)}</button>')
    parts.append('</div></div>')
    parts.append('<p class="count" id="count"></p>')

    for ticket, items in groups.items():
        task = next((i["ToDo/タスク名"] for i in items if i["ToDo/タスク名"]), "")
        parts.append('<section class="tk">')
        parts.append(f'<h2>{esc(ticket)}<span class="task">{esc(task)}</span></h2>')
        for r in items:
            key = " ".join([
                r["チケットID"], r["成果物タイトル"], r["種別"],
                r["内容（要約）"], r["ToDo/タスク名"], r["リポジトリ相対パス"],
            ]).lower()
            pub_cls = "pub-gh" if r["公開状態"] == "GitHub公開" else "pub-local"
            href = "file://" + r["ローカルリンク"].replace(" ", "%20")
            parts.append(
                f'<div class="row" data-kind="{esc(r["種別"])}" data-k="{esc(key)}">'
                f'<a class="t" href="{esc(href)}">{esc(r["成果物タイトル"])}</a>'
                f'<div class="meta">'
                f'<span class="tag">{esc(r["種別"])}</span>'
                f'<span class="tag">{esc(r["形式"])}</span>'
                f'<span class="tag {pub_cls}">{esc(r["公開状態"])}</span>'
                f'<span>{esc(r["作成日"])}</span>'
                f'<span>{esc(r["担当"])}</span>'
                + ('<span class="tag todo">要約 要記入</span>'
                   if r["内容（要約）"] == NEEDS_INPUT else "")
                + '</div>'
            )
            if r["内容（要約）"] and r["内容（要約）"] != NEEDS_INPUT:
                parts.append(
                    f'<details class="sum"><summary>要約</summary>{esc(r["内容（要約）"])}'
                    + (f'<br><b>暫定結果：</b>{esc(r["暫定結果"])}' if r["暫定結果"] else "")
                    + (f'<br><b>備考：</b>{esc(r["備考"])}' if r["備考"] else "")
                    + '</details>'
                )
            parts.append("</div>")
        parts.append("</section>")
    parts.append(HTML_TAIL)

    new = "".join(parts)
    old = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = f.read()
    # 生成日の1行だけが違う再実行で毎回差分を出さないよう、日付行を無視して比較する。
    def strip_date(s: str) -> str:
        return re.sub(r"生成 \d{4}-\d{2}-\d{2}。", "", s or "")
    if old is not None and strip_date(old) == strip_date(new):
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    return True


# ── 追跡漏れの検知 ──────────────────────────────────────────────────────────
def untracked_candidates(files: list[str], tracked: set[str]) -> list[tuple[str, str]]:
    """
    「成果物に見えるのに git 追跡されていない」ファイルと、その除外理由を返す。

    理由は `git check-ignore -v` が返す .gitignore の行そのもの。
    `*`（全除外）のような catch-all で落ちているなら、それは意図ではなく事故。
    理由が具体的なパターン（`*.csv` 等）なら、意図した除外である可能性が高い。
    ここでは判定せず、**人が3秒で判断できる情報を出す**（memory: 検知はしろ、自動同期はするな）。
    """
    out = []
    for rel in files:
        if rel in tracked:
            continue
        why = run_git(["check-ignore", "-v", rel]).strip().splitlines()
        reason = why[0] if why else "（.gitignore に該当なし＝単に git add されていない）"
        out.append((rel, reason))
    return out


def cmd_check_untracked(files, tracked) -> int:
    cands = untracked_candidates(files, tracked)
    if not cands:
        print("[OK] 未追跡の成果物候補はありません。")
        return 0
    catchall = [c for c in cands if re.search(r":\d+:\*\s", c[1]) or c[1].endswith(":*")]
    print(f"[警告] 未追跡の成果物候補 {len(cands)} 件"
          f"（うち catch-all `*` による除外 {len(catchall)} 件）")
    for rel, reason in cands:
        print(f"  - {rel}\n      理由: {reason}")
    print("\n判断のしかた: 理由が `*`（全除外）なら追記漏れの疑いが濃い。"
          "`*.csv` のような具体パターンなら意図した除外の可能性が高い。"
          "公開してよいかの判断は社長・法務の領分です（勝手に git add しないこと）。")
    return 1


def cmd_warn_for_commit(files, tracked) -> int:
    """pre-commit から呼ばれる。catch-all で落ちているものだけを警告する（止めない）。"""
    cands = untracked_candidates(files, tracked)
    catchall = [c for c in cands if re.search(r":\d+:\*\s", c[1]) or c[1].endswith(":*")]
    if catchall:
        print("⚠️  deliverables に catch-all `*` で除外されたファイルがあります"
              f"（{len(catchall)} 件）。許可リストへの追記漏れの疑いがあります:")
        for rel, reason in catchall[:10]:
            print(f"     - {rel}  ({reason})")
        print("     確認: python3 scripts/catalog/build_catalog.py --check-untracked")
    return 0


# ── main ────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="成果物カタログを deliverables から機械生成する")
    ap.add_argument("--dry-run", action="store_true", help="書き込まず件数だけ出す")
    ap.add_argument("--check-untracked", action="store_true", help="追跡漏れを検知して一覧する")
    ap.add_argument("--warn-untracked-for-commit", action="store_true",
                    help="pre-commit 用。catch-all 除外だけを警告する（常に成功で終わる）")
    args = ap.parse_args()

    os.chdir(REPO_ROOT)
    files = scan_files()
    tracked = tracked_paths()

    if args.check_untracked:
        return cmd_check_untracked(files, tracked)
    if args.warn_untracked_for_commit:
        return cmd_warn_for_commit(files, tracked)

    existing, all_existing = load_existing(CSV_PATH)
    rows = build_rows(files, existing, all_existing, tracked, current_branch())

    carried_n = sum(1 for r in rows if r["内容（要約）"] != NEEDS_INPUT)
    todo_n = len(rows) - carried_n
    local_only = sum(1 for r in rows if r["公開状態"] == "ローカルのみ")
    kept_paths = {r["リポジトリ相対パス"] for r in rows}
    lost = [p for p in existing if p not in kept_paths]
    kept_prose = sum(1 for r in all_existing
                     if (r.get("リポジトリ相対パス") or "").strip() in kept_paths)

    print(f"走査 {len(files)} ファイル / 既存 CSV {len(all_existing)} 行"
          f"（うち {kept_prose} 行ぶんのパスを引き継ぎ）")
    print(f"生成 {len(rows)} 行（要約 引き継ぎ {carried_n} / 要記入 {todo_n} / ローカルのみ {local_only}）")
    if lost:
        print(f"⚠️  既存 CSV にあってファイルが見つからない行 {len(lost)} 件（除外フィルタ or 移動）:")
        for p in lost[:20]:
            print(f"     - {p}")

    if args.dry_run:
        print("(--dry-run のため書き込みませんでした)")
        return 0

    changed_csv = write_csv(CSV_PATH, rows)
    changed_html = write_html(HTML_PATH, rows)
    print(f"CSV : {CSV_PATH} … {'更新' if changed_csv else '差分なし'}")
    print(f"HTML: {HTML_PATH} … {'更新' if changed_html else '差分なし'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
