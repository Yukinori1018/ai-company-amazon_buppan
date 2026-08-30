#!/usr/bin/env python3
"""根拠（チケット本文・memory）を機械で突き合わせる。

    python3 evidence.py extract <deliverables_dir> <work_dir>   … 抜粋と索引を作る（prepare）
    python3 evidence.py check   <deliverables_dir> <work_dir>   … 実在・鮮度・整合を検査（build）

2026-08-31 の全数再検証で出た誤判定の型は4つでした。このスクリプトはそのうち3つを機械で潰します。

  ① タイトルと要約だけで判定した → `extract` が根拠チケットの本文を1ファイルに集める。
     読まずには判定できない状態にする。
  ② 資料の日付が凍結して、あとから覆った事実を取り込めていない → `check` が
     「資料の更新日より新しいチケット」と「prepare 以降に書き換わったチケット」を NG にする。
  ④ 根拠IDが実在しない／本文に該当記述が無い → `check` が実在とキーワード共起を見る。

③（動詞の読み違い）は完全には機械化できません。`check` は「満たす」「提出する」等の
物理事実を表す動詞で終わる小項目が `[x]` のとき、根拠に裏書きの一言があるかだけを問います。
最後は人が本文を読んで決めます。
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
from datetime import date

# ---------------------------------------------------------------- 定数

TICKET_ID = re.compile(r"T-\d{8}-\d{3}")
MEMORY_REF = re.compile(r"memory:\s*([A-Za-z0-9_\-./]+)")
RE_TASK = re.compile(r"^- \[([x~ ])\] (.*)$")
RE_REFS = re.compile(r"〔([^〕]*)〕")
RE_DOC_DATE = re.compile(r"更新:\s*(\d{4}-\d{2}-\d{2})")
RE_UPDATED_AT = re.compile(r"^updated_at:\s*(\S+)", re.M)
RE_TITLE = re.compile(r"^title:\s*(.+)$", re.M)
RE_TICKET_ID_FM = re.compile(r"^ticket_id:\s*(\S+)", re.M)

# 抜き出すセクション。見出しの「前方一致」で拾う（現場の見出しは揺れている：
# 「完了報告」「完了報告（カズヨ宛）」「ログ」「ログ追記」「ログ（追記）」…）。
# (見出しの接頭辞, 何文字まで, 末尾から取るか)
SECTIONS = [
    ("現在地", 600, False),
    ("完了報告", 800, False),
    ("結果", 600, False),
    ("裏どり", 600, False),
    ("納品", 500, False),
    ("成果物", 400, False),
    ("社長判断待ち", 400, False),
    ("ログ", 900, True),  # 時系列なので新しい末尾を見る
]

# 物理事実を表す動詞。ここで終わる小項目は「調べた」では [x] にならない。
# 2026-08-31 追加: 満たす / 一致させる / 揃える / 切り替える
#   7-1「カート獲得の5条件を満たす」を「条件を確認した」と読み替えて [x] にしていた。
#   根拠チケット自身が「小口ではカートを獲得できない」と書いていたので誤判定です。
ACTION_VERBS = [
    "取得する",
    "提出する",
    "送る",
    "発注する",
    "登録する",
    "満たす",
    "一致させる",
    "揃える",
    "切り替える",
]

# 根拠の注記に1語でも入っていれば「裏書きあり」とみなす語。
CONFIRM_WORDS = ["確認", "完了", "送信", "提出", "受信", "実施", "取得", "一致", "画面", "実測"]

# キーワード共起の判定から外す語。どのチケットにも出るので識別力がない。
STOPWORDS = {
    "確認", "対応", "設定", "作成", "実施", "検討", "判断", "整理", "記録", "報告",
    "必要", "場合", "以下", "以上", "以内", "自分", "今回", "今後", "現在", "状態",
    "内容", "情報", "項目", "方法", "手順", "基準", "条件", "理由", "結果", "問題",
    "アカウント", "チケット", "ファイル",
}


# ---------------------------------------------------------------- 読み取り

def sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def repo_root(here: str) -> str:
    return os.path.abspath(os.path.join(here, "..", "..", "..", ".."))


def memory_dirs(repo: str) -> list[str]:
    """memory ファイルの置き場。プロジェクト自動メモリ＋各エージェントの memory/。"""
    slug = re.sub(r"[^A-Za-z0-9]", "-", repo)
    dirs = [os.path.expanduser(f"~/.claude/projects/{slug}/memory")]
    agents = os.path.join(repo, "agents")
    if os.path.isdir(agents):
        dirs += [
            os.path.join(agents, a, "memory")
            for a in sorted(os.listdir(agents))
            if os.path.isdir(os.path.join(agents, a, "memory"))
        ]
    return [d for d in dirs if os.path.isdir(d)]


def index_tickets(tickets_dir: str) -> tuple[dict[str, str], set[str]]:
    """{ticket_id: path} と、重複採番された id の集合を返す。"""
    found: dict[str, list[str]] = {}
    for folder in ("done", "doing", "waiting", "todo"):
        d = os.path.join(tickets_dir, folder)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith(".md") or name.startswith("_"):
                continue
            path = os.path.join(d, name)
            text = open(path, encoding="utf-8").read(4000)
            m = RE_TICKET_ID_FM.search(text)
            tid = m.group(1) if m else name.split("_")[0]
            found.setdefault(tid, []).append(path)
    dup = {k for k, v in found.items() if len(v) > 1}
    return {k: v[0] for k, v in found.items()}, dup


def section_text(text: str, prefix: str, limit: int, tail: bool) -> str:
    """'## <prefix>…' セクションの中身を取り出す。同名が複数あれば連結する。"""
    chunks = []
    for m in re.finditer(rf"^##+ {re.escape(prefix)}[^\n]*\n(.*?)(?=^##+ |\Z)", text, re.S | re.M):
        body = m.group(1).strip()
        if body:
            chunks.append(body)
    if not chunks:
        return ""
    joined = "\n".join(chunks)
    if len(joined) <= limit:
        return joined
    return ("…（前略）\n" + joined[-limit:]) if tail else (joined[:limit] + "\n…（後略）")


def ticket_excerpt(path: str) -> tuple[dict[str, str], dict[str, str]]:
    """(frontmatter の抜粋, {セクション名: 抜粋})"""
    text = open(path, encoding="utf-8").read()
    meta = {
        "folder": os.path.basename(os.path.dirname(path)),
        "title": (RE_TITLE.search(text).group(1).strip() if RE_TITLE.search(text) else ""),
        "updated_at": (
            RE_UPDATED_AT.search(text).group(1).strip('"\'') if RE_UPDATED_AT.search(text) else ""
        ),
    }
    secs = {}
    for prefix, limit, tail in SECTIONS:
        body = section_text(text, prefix, limit, tail)
        if body:
            secs[prefix] = body
    return meta, secs


# ---------------------------------------------------------------- 小項目の解析

def strip_markup(s: str) -> str:
    s = RE_REFS.sub("", s)
    s = re.sub(r"`\[[^\]]*\]`", "", s)  # `[社長]` `[AI]` などの担当タグ
    s = s.replace("**", "").replace("⚠️", "")
    return s.strip()


def parse_items(master: str) -> list[dict]:
    items = []
    for lineno, line in enumerate(open(master, encoding="utf-8"), 1):
        m = RE_TASK.match(line.rstrip("\n"))
        if not m:
            continue
        mark, raw = m.group(1), m.group(2)
        refs = " ".join(RE_REFS.findall(raw))
        items.append(
            {
                "lineno": lineno,
                "mark": mark,
                "body": strip_markup(raw),
                "refs_raw": refs,
                "tickets": sorted(set(TICKET_ID.findall(refs))),
                "memories": sorted(set(MEMORY_REF.findall(refs))),
                # ID と memory 参照を除いた残り＝人が書いた裏書きの注記
                "note": MEMORY_REF.sub("", TICKET_ID.sub("", refs)).strip(" /・、。"),
            }
        )
    return items


def keywords(body: str, limit: int = 8) -> list[str]:
    """識別力のありそうな語を長い順に拾う。形態素解析は使わない（依存を増やさない）。"""

    def grab(n: int) -> set[str]:
        c = set(re.findall(rf"[ァ-ヴー]{{{n},}}", body))
        c |= set(re.findall(rf"[一-龥々]{{{n},}}", body))
        c |= set(re.findall(rf"[A-Za-z][A-Za-z0-9]{{{n - 1},}}", body))
        return c - STOPWORDS

    cands = grab(3)
    if len(cands) < 2:  # 「2段階認証を設定する」のように長い語が取れない短文の保険
        cands |= grab(2)
    return sorted(cands, key=len, reverse=True)[:limit]


def evidence_pool(tid: str, path: str, repo: str, self_ticket: str) -> str:
    """そのチケットが根拠として差し出せる文字列。本文＋そのチケットの成果物。

    成果物まで含めるのは、「事実は成果物に書き、チケット本文は経緯だけ」という
    書き方が普通にあるからです。本文だけを見ると正当な引用まで警告になり、
    警告が信用されなくなります。自分自身（マスターToDo）の成果物だけは除きます
    ——208項目の本文が全部入っているので、何を照合しても必ず当たってしまいます。
    """
    text = open(path, encoding="utf-8").read()
    if tid == self_ticket:
        return text
    d = os.path.join(repo, "workspace", "output", "deliverables", tid)
    if not os.path.isdir(d):
        return text
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        if not name.endswith((".md", ".csv", ".txt", ".html")) or os.path.getsize(p) > 600_000:
            continue
        body = open(p, encoding="utf-8", errors="ignore").read()
        if name.endswith(".html"):
            body = html.unescape(re.sub(r"<[^>]+>", " ", body))
        text += "\n" + body
    return text


def ends_with_action_verb(body: str) -> str | None:
    """先頭の一文が物理事実の動詞で終わるならその動詞を返す。"""
    head = re.split(r"[。（(]", body)[0].strip()
    for v in ACTION_VERBS:
        if head.endswith(v):
            return v
    return None


# ---------------------------------------------------------------- extract

def build_index(deliv: str, tickets_dir: str) -> dict:
    master = os.path.join(deliv, "01_master-todo.md")
    text = open(master, encoding="utf-8").read()
    m = RE_DOC_DATE.search(text)
    paths, dup = index_tickets(tickets_dir)
    items = parse_items(master)

    # 小項目からの参照だけでなく、A章の表や narrative の参照も拾う。
    # 2026-08-31 の日付凍結（型②）は、まさに narrative 側で起きました。
    cited: dict[str, list[dict]] = {t: [] for t in sorted(set(TICKET_ID.findall(text)))}
    for it in items:
        for tid in it["tickets"]:
            cited.setdefault(tid, []).append(it)

    entry = {}
    missing = []
    for tid in sorted(cited):
        p = paths.get(tid)
        if not p:
            missing.append(tid)
            continue
        entry[tid] = {
            "path": os.path.relpath(p, repo_root(os.path.dirname(os.path.abspath(__file__)))),
            "abspath": p,
            "sha256": sha256(p),
        }
    return {
        "doc_date": m.group(1) if m else "",
        "self_ticket": os.path.basename(deliv.rstrip("/")),
        "duplicate_ticket_ids": sorted(dup),
        "missing_tickets": missing,
        "tickets": entry,
        "cited": cited,  # メモリ上だけで使う（JSON には落とさない）
        "items": items,
    }


def write_excerpts(idx: dict, out_md: str, repo: str) -> None:
    doc_date = idx["doc_date"]
    lines = [
        "# 根拠チケット本文の抜粋（判定の入力）",
        "",
        "**この抜粋を読んでからマークを更新してください。** タイトルと要約だけで判定すると",
        "2026-08-31 の10件と同じ誤判定になります（開業日 8/20 を提出日と取り違えた等）。",
        "",
        f"- 資料の更新日: **{doc_date or '不明'}**",
        f"- 参照されているチケット: {len(idx['tickets'])} 枚",
        "",
    ]

    stale = []
    for tid in sorted(idx["tickets"]):
        u = ticket_excerpt(idx["tickets"][tid]["abspath"])[0]["updated_at"]
        if u and doc_date and u > doc_date:
            stale.append((tid, u))

    if idx["missing_tickets"]:
        lines += [
            "## ⚠ 実在しない根拠ID",
            "",
            "資料に書かれているが、`workspace/tickets/` にファイルが無いものです。",
            "",
            *[f"- {t}" for t in idx["missing_tickets"]],
            "",
        ]
    if stale:
        lines += [
            "## ⚠ 資料より新しいチケット（日付凍結のリスク）",
            "",
            "資料の更新日より後に動いています。**資料の記述が覆っている可能性があります。**",
            "",
            *[f"- {t}（updated_at: {u}）" for t, u in stale],
            "",
        ]

    lines += ["---", ""]
    for tid in sorted(idx["tickets"]):
        v = idx["tickets"][tid]
        meta, secs = ticket_excerpt(v["abspath"])
        cites = idx["cited"][tid]
        lines += [
            f"## {tid} — {meta['title']}",
            "",
            f"`{v['path']}` ／ 状態: {meta['folder']} ／ updated_at: {meta['updated_at'] or '不明'}"
            f" ／ この ID を根拠にしている小項目: {len(cites)} 件",
            "",
        ]
        for it in cites:
            lines.append(f"- `[{it['mark']}]` {it['body'][:70]}")
        lines.append("")
        if not secs:
            lines += ["> 本文に「現在地」「完了報告」「結果」「ログ」がありません。", ""]
        for name, body in secs.items():
            lines += [f"### {name}", "", body, ""]
        lines += ["---", ""]

    # memory 出典も同じ扱いで冒頭だけ載せる（〔memory: …〕＝知識の出典）。
    mems: dict[str, list[dict]] = {}
    for it in idx["items"]:
        for name in it["memories"]:
            mems.setdefault(name, []).append(it)
    if mems:
        lines += ["## memory 出典", ""]
        dirs = memory_dirs(repo)
        for name in sorted(mems):
            path = next(
                (os.path.join(d, name + ".md") for d in dirs if os.path.exists(os.path.join(d, name + ".md"))),
                "",
            )
            head = ""
            if path:
                head = open(path, encoding="utf-8").read(400).strip()
            lines += [
                f"### memory: {name} — {'見つかった' if path else '**ファイルが見つからない**'}",
                "",
                *[f"- `[{it['mark']}]` {it['body'][:70]}" for it in mems[name]],
                "",
            ]
            if head:
                lines += ["```", head, "```", ""]

    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def cmd_extract(deliv: str, work: str, repo: str) -> int:
    idx = build_index(deliv, os.path.join(repo, "workspace", "tickets"))
    os.makedirs(work, exist_ok=True)
    out_md = os.path.join(work, "02_evidence-excerpts.md")
    write_excerpts(idx, out_md, repo)

    slim = {
        "generated_at": date.today().isoformat(),
        "doc_date": idx["doc_date"],
        "self_ticket": idx["self_ticket"],
        "missing_tickets": idx["missing_tickets"],
        "tickets": {t: {"path": v["path"], "sha256": v["sha256"]} for t, v in idx["tickets"].items()},
    }
    with open(os.path.join(work, "02_evidence-index.json"), "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False, indent=1)

    print(f"evidence: {out_md}（{len(idx['tickets'])} 枚 / {os.path.getsize(out_md) // 1024} KB）")
    print("  ↑ マークを更新する前にこれを読むこと。タイトルだけの判定が誤判定の最多要因です。")
    if idx["missing_tickets"]:
        print("!! 実在しない根拠ID: " + ", ".join(idx["missing_tickets"]))
    if idx["duplicate_ticket_ids"]:
        print("!! ticket_id の重複（カズヨへ要報告）: " + ", ".join(idx["duplicate_ticket_ids"]))
    return 0


# ---------------------------------------------------------------- check

def cmd_check(deliv: str, work: str, repo: str) -> int:
    idx = build_index(deliv, os.path.join(repo, "workspace", "tickets"))
    errors: list[str] = []
    warns: list[str] = []

    # (a) 実在しない根拠ID = 事実の誤り。NG。
    for tid in idx["missing_tickets"]:
        errors.append(f"根拠ID {tid} のチケットファイルが実在しない")

    # (b) 鮮度 — 資料の更新日より後に動いたチケット。資料が覆っている可能性がある。
    doc_date = idx["doc_date"]
    if not doc_date:
        errors.append("01_master-todo.md の見出しに「更新: YYYY-MM-DD」が無い")
    else:
        newer = []
        for tid, v in sorted(idx["tickets"].items()):
            u = ticket_excerpt(v["abspath"])[0]["updated_at"]
            if u and u > doc_date:
                newer.append(f"{tid}（{u}）")
        if newer:
            errors.append(
                "資料の更新日 " + doc_date + " より新しいチケットがある: " + ", ".join(newer)
            )

    # (c) prepare 以降に書き換わったチケット。読んだ内容と今の内容が違う。
    ipath = os.path.join(work, "02_evidence-index.json")
    if not os.path.exists(ipath):
        errors.append(f"{ipath} が無い（先に `todo.sh prepare` を実行して根拠抜粋を作ること）")
    else:
        snap = json.load(open(ipath, encoding="utf-8"))
        me = idx["self_ticket"]
        changed, unread = [], []
        for tid, v in sorted(idx["tickets"].items()):
            if tid == me:
                continue  # 自分の作業ログは根拠ではないので鮮度検査から外す
            s = snap["tickets"].get(tid)
            if not s:
                unread.append(tid)
            elif s["sha256"] != v["sha256"]:
                changed.append(tid)
        if changed:
            errors.append(
                "prepare 以降に本文が変わったチケット（抜粋を作り直して読み直すこと）: "
                + ", ".join(changed)
            )
        if unread:
            warns.append(
                "prepare 時点の抜粋に無い根拠ID（本文を読んで付けたか確認）: " + ", ".join(unread)
            )

    # (d) キーワード共起 — 根拠チケットの本文にも成果物にも小項目の語が1語も出てこない。
    texts: dict[str, str] = {
        tid: evidence_pool(tid, v["abspath"], repo, idx["self_ticket"])
        for tid, v in idx["tickets"].items()
    }
    for it in idx["items"]:
        if not it["tickets"]:
            continue
        if len(it["note"]) >= 6:
            continue  # 人が裏書きの一言を書いている＝それ自体が根拠。機械は口を出さない
        kws = keywords(it["body"])
        if not kws:
            continue
        pool = "\n".join(texts.get(t, "") for t in it["tickets"])
        if not pool:
            continue
        if not any(k in pool for k in kws):
            warns.append(
                f"{it['lineno']}行目 根拠チケットの本文にも成果物にも該当語が無い "
                f"〔{'/'.join(it['tickets'])}〕: {it['body'][:44]}"
            )

    # (e) 動詞テスト — 物理事実の動詞なのに裏書きの一言が無い [x]。
    for it in idx["items"]:
        if it["mark"] != "x":
            continue
        v = ends_with_action_verb(it["body"])
        if not v:
            continue
        if not it["tickets"] and not it["memories"]:
            warns.append(f"{it['lineno']}行目 「{v}」なのに根拠が無い [x]: {it['body'][:44]}")
        elif not any(w in it["note"] for w in CONFIRM_WORDS):
            warns.append(
                f"{it['lineno']}行目 「{v}」＝物理事実。根拠に裏書きの一言が無い "
                f"（例: 〔T-…・画面確認〕）: {it['body'][:44]}"
            )

    # (f) memory 出典の実在
    dirs = memory_dirs(repo)
    if dirs:
        for it in idx["items"]:
            for name in it["memories"]:
                if not any(os.path.exists(os.path.join(d, name + ".md")) for d in dirs):
                    errors.append(f"{it['lineno']}行目 〔memory: {name}〕のファイルが見つからない")

    for e in errors:
        print(f"  NG {e}")
    for w in warns:
        print(f"  ▲ {w}")
    if not errors:
        print(f"  OK 根拠の実在・鮮度・整合（参照 {len(idx['tickets'])} 枚 / 警告 {len(warns)} 件）")
    return 1 if errors else 0


# ---------------------------------------------------------------- entry

def main() -> int:
    if len(sys.argv) != 4 or sys.argv[1] not in ("extract", "check"):
        print(__doc__)
        return 2
    cmd, deliv, work = sys.argv[1], sys.argv[2], sys.argv[3]
    repo = repo_root(os.path.dirname(os.path.abspath(__file__)))
    return cmd_extract(deliv, work, repo) if cmd == "extract" else cmd_check(deliv, work, repo)


if __name__ == "__main__":
    raise SystemExit(main())
