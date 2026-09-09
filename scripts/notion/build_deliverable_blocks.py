#!/usr/bin/env python3
"""
build_deliverable_blocks.py — チケットの `## 成果物` 節を Notion カード本文用に変換する。

なぜ要るのか（1行）:
    社長が見るのは Notion のカード。ローカルの `.md` に成果物節を書いただけでは
    「やっていないのと同じ」になる（2026-09-09 社長指摘 / T-20260909-004）。

何をするか:
    workspace/tickets/{todo,doing,waiting,done}/*.md を全部読み、
    各チケットの `## 成果物` 節を取り出して、Notion に貼れる Markdown に直す。

    変換は3つだけ:
      1. 相対リンク `../../output/deliverables/<path>` → `http://localhost:17325/<path>`
         （ポートは環境変数 CATALOG_PORT。build_catalog.py と必ず揃えること）
         パスは日本語ファイル名を含むので、セグメントごとに percent-encode する。
      2. `**強調**` を落とす（Notion のカード本文では読みにくいだけ）。
      3. リンクラベルのバッククォートを外す（`[`a.md`](url)` → `[a.md](url)`）。

    リンクを1本でも含むチケットには、末尾に配信サーバの起動方法を1行だけ添える。
    成果物が無いチケットは `（なし — 理由）` の行がそのまま残る（欄ごと省略しない）。

出力:
    --json <path>   {ticket_id: {"content": "...", "status": "..."}} を書き出す
    （既定）        標準出力に `=== <ticket_id>` 区切りで表示

Notion への書き込みは**このスクリプトでは行わない**。
ホスト型 Notion MCP（`notion-update-page` / command="insert_content"）でしか書けず、
ローカルにトークンが無いため。手順は
agents/general_affairs/skills/notion-ticket-sync.md §成果物節の Notion 反映 を参照。

使い方:
    python3 scripts/notion/build_deliverable_blocks.py
    python3 scripts/notion/build_deliverable_blocks.py --json /tmp/payload.json
    python3 scripts/notion/build_deliverable_blocks.py --check-links   # 全URLに GET して 200 を確認
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from glob import glob
from urllib.parse import quote

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TICKETS_DIR = os.path.join(REPO_ROOT, "workspace", "tickets")
STATES = ("todo", "doing", "waiting", "done")

# build_catalog.py の CATALOG_PORT と必ず揃えること。
PORT = os.environ.get("CATALOG_PORT", "17325")
SERVE_BASE = f"http://localhost:{PORT}"

SERVER_NOTE = (
    "\n\n※ 上のリンクはローカル配信サーバ起動中のみ開けます"
    "（`python3 scripts/catalog/serve_deliverables.py`）。"
)

REL_LINK = re.compile(r"\]\(\.\./\.\./output/deliverables/([^)]*)\)")
SECTION = re.compile(r"^## 成果物\s*$(.*?)(?=^## |\Z)", re.M | re.S)
CODE_LABEL = re.compile(r"\[`([^`]+)`\]")


def serve_url(rel: str) -> str:
    """deliverables 配下の相対パス → 配信サーバの URL。末尾スラッシュは保つ。"""
    trailing = "/" if rel.endswith("/") else ""
    parts = [p for p in rel.strip("/").split("/") if p]
    return f"{SERVE_BASE}/" + "/".join(quote(p) for p in parts) + trailing


def convert(section: str) -> str:
    s = REL_LINK.sub(lambda m: f"]({serve_url(m.group(1))})", section)
    s = s.replace("**", "")
    s = CODE_LABEL.sub(r"[\1]", s)
    return s


def collect() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for state in STATES:
        for path in sorted(glob(os.path.join(TICKETS_DIR, state, "*.md"))):
            text = open(path, encoding="utf-8").read()
            m_id = re.search(r"^ticket_id:\s*(\S+)", text, re.M)
            if not m_id:
                print(f"[WARN] ticket_id なし: {path}", file=sys.stderr)
                continue
            tid = m_id.group(1)
            m_sec = SECTION.search(text)
            if not m_sec:
                print(f"[WARN] `## 成果物` 節なし: {path}", file=sys.stderr)
                body = "（なし — 節が未整備。チケット本体を先に直してください）"
            else:
                body = convert(m_sec.group(1).strip())
            content = "## 成果物\n\n" + body
            if SERVE_BASE in content:
                content += SERVER_NOTE
            out[tid] = {"content": content, "status": state, "file": path}
    return out


def check_links(data: dict[str, dict]) -> int:
    urls = sorted({u for v in data.values() for u in re.findall(r"\((http://localhost[^)]*)\)", v["content"])})
    bad = []
    for u in urls:
        try:
            code = urllib.request.urlopen(u, timeout=5).status
        except Exception as e:  # noqa: BLE001
            code = getattr(e, "code", repr(e))
        if code != 200:
            bad.append((u, code))
    print(f"[check] {len(urls)} URL / non-200 {len(bad)}")
    for u, c in bad:
        print(f"  {c}  {u}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="チケットの成果物節を Notion 本文用に変換する")
    ap.add_argument("--json", help="変換結果を JSON で書き出す")
    ap.add_argument("--check-links", action="store_true", help="全 URL に GET して 200 を確認する")
    args = ap.parse_args()

    data = collect()
    print(f"[OK] チケット {len(data)} 件を読み込みました（{SERVE_BASE}）", file=sys.stderr)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        print(f"[OK] 書き出し: {args.json}", file=sys.stderr)
    elif not args.check_links:
        for tid in sorted(data):
            print(f"=== {tid}")
            print(data[tid]["content"])

    if args.check_links:
        return check_links(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
