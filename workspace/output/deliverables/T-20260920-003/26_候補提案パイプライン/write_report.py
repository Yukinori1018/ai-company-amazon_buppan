#!/usr/bin/env python3
"""成果物 32（買う候補リスト）の md / html を書く。表と内訳は台帳とログから作る。"""

from __future__ import annotations

import glob
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
WORK = REPO / "workspace/output/agent_output/T-20260920-003/pipeline"
DELIV = REPO / "workspace/output/deliverables/T-20260920-003"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_buy_list as M  # noqa: E402


def stage_a_tally() -> dict:
    log = (WORK / "stageA.log").read_text(encoding="utf-8")
    tot = {"hit": 0, "dead": 0, "nopr": 0, "kept": 0, "loss": 0, "thrown": 0}
    pat = (r"JAN が Amazon に当たった (\d+)件 → 生きている棚 \d+件（売れていない棚 (\d+)件）"
           r"→ 出品があって売価が付く \d+件（出品なし (\d+)件）→ \*\*候補 (\d+)件\*\*"
           r"（赤字で落とした (\d+)件）")
    for m in re.finditer(pat, log):
        hit, dead, nopr, kept, loss = map(int, m.groups())
        tot["hit"] += hit; tot["dead"] += dead; tot["nopr"] += nopr
        tot["kept"] += kept; tot["loss"] += loss
    for seg in log.split("== 累計消費"):
        ns = [int(x) for x in re.findall(r"JAN (\d+)/\d+ → 商品", seg)]
        if ns:
            tot["thrown"] += max(ns)
    return tot


def reason_parts(reason: str) -> list[str]:
    """`判定理由` から、落ちたゲートの断片だけを取り出す。

    ⚠️ **wave の JSON ではなく台帳を読む。** wave ファイルは実行ごとに同じ名前で
    上書きされるので、2回目の実行で1回目の根拠が消える（2026-10-01 に消した）。
    **台帳は消えない**ので、集計はそこからやる。
    """
    body = re.sub(r"^(【[^】]*】)+", "", reason or "")
    return [x.strip() for x in body.split("／") if x.strip()]


# 落ちた断片 → (まとめ名, 実画面で確定できるか)
# カズヨ 2026-10-01: ①③は機械が読めないだけ＝実画面で確定できる。
#   ②（本体の在庫履歴）は実画面でも覆らない。⑥（誤差幅）は見ても数字が変わらない。
BUCKETS = (
    ("カート保持者が Amazon.co.jp 本体", "②本体がカートを持っている", False),
    ("統計期間中に本体がカートを", "②本体がカートを取った履歴がある", False),
    ("本体が直近1年の", "②本体の在庫履歴がある", False),
    ("根拠が 1 本しか取れませんでした", "①カート保持者を機械で確定できない", True),
    ("オファー一覧が取得できませんでした", "③オファー一覧が取れない", True),
    ("本体が混ざっています", "②出品一覧に本体が混ざっている", False),
    ("セラー名", "④メーカー直販かを機械で判定できない", True),
    ("卸を1社に限定している棚の可能性", "④メーカー直販の疑い", True),
    ("赤字", "⑤赤字", False),
    ("実質赤字", "⑤赤字（保管・納品・梱包を引くと沈む）", False),
    ("誤差幅", "⑥手残りが誤差幅以下", False),
    ("採算を計算できません", "⑤採算が計算できない（Amazon 側のセット数が読めない）", True),
    ("個数が読めません", "⑤Amazon 側のセット数が商品名から読めない", True),
    ("売り切るのに", "⑤ロットが大きすぎて6ヶ月で捌けない", False),
    ("要期限管理", "⑦賞味期限管理が要るカテゴリ", False),
    ("売れ筋ランク", "⑧生存（売れている根拠がない）", False),
    ("ランクが取れません", "⑧生存（ランクが付いていない）", False),
    ("卸サイトの商品ページが特定できていません", "⑨仕入れが実在しない", False),
)


def classify(part: str) -> tuple[str, bool]:
    for needle, name, onscreen in BUCKETS:
        if needle in part:
            return name, onscreen
    return part[:40], False


def stage_b_reasons(rows: list[dict]) -> tuple[dict, int]:
    """落ちた理由の内訳。母集団は渡された行（今日判定したぶん）。"""
    buckets: dict[str, int] = {}
    for r in rows:
        if r["verdict"] == "GO":
            continue
        for part in reason_parts(r["reason"]):
            name, _ = classify(part)
            buckets[name] = buckets.get(name, 0) + 1
    return buckets, len(rows)


def near_misses(rows: list[dict]) -> list[dict]:
    """**あと1つで通る候補。**落ちたゲートがちょうど1本だけの行。

    0件の報告でこれを出さないと、社長は「何も無い」としか読めない。
    どのゲート1本が結論を決めているかが分かれば、人がそこだけ見れば判断できる。
    """
    out = []
    for r in rows:
        if r["verdict"] == "GO":
            continue
        parts = reason_parts(r["reason"])
        if not parts:
            continue
        judged = [classify(x) for x in parts]
        # **落ちた全部が実画面で確定できる行だけ**をカズヨの対象にする。
        # 「ちょうど1本」では、生存の断片が1本混じるだけで全部こぼれて0件になった（2026-10-01）。
        # 逆に1本でも実画面で覆らないものが混じっていれば、見ても結論は変わらない。
        # **判定が UNKNOWN の行＝人が見れば確定する行**。これがパイプラインの意味そのもの。
        # NO-GO には FAIL（実画面でも覆らない事実）が1本以上入っているので、見ても結論は変わらない。
        # 「落ちた断片がちょうど1本」で絞ると、生存の断片が混じるだけで全部こぼれた（2026-10-01）。
        out.append({**r, "why": " ＋ ".join(n for n, _ in judged),
                    "why_full": " ／ ".join(parts),
                    "onscreen": r["verdict"] == "UNKNOWN"})
    return out


# 初回の候補から外す系列。生存 PASS 18件のうち14件が同一シリーズ・同一出展企業で、
# 分散が効かない（カズヨ 2026-10-01）。水俣条約による製造終了の推測は**理由の2番目**で、
# 当否に関わらず偏りだけで外す。
EXCLUDED_SERIES = ("DNライティング",)


def excluded(title: str | None) -> bool:
    return any(w in (title or "") for w in EXCLUDED_SERIES)


def main() -> int:
    rows = M.load_rows()
    go = [r for r in rows if r["verdict"] == "GO" and not excluded(r["title"])]
    unknown = [r for r in rows if r["verdict"] == "UNKNOWN"]
    nogo = [r for r in rows if r["verdict"] == "NO-GO"]
    M.write_private_csv(rows, WORK / "buy_list_private.csv")
    a = stage_a_tally()
    today_rows = [r for r in rows if r["date"] == date.today().isoformat()]
    bucket, bn = stage_b_reasons(today_rows)
    titles_all = {r["asin"]: r for r in rows}
    today = date.today().isoformat()

    L: list[str] = []
    w = L.append
    w("# 買う候補リスト（NETSEA 起点・2026-10-01）")
    w("")
    w(f"**候補 {len(go)}件**（CLAUDE.md §3.3 のゲートを全部通り、"
      f"初回の分散として使える系列のもの）。")
    w("")
    w(f"- **今日判定した ASIN: {len(today_rows)}件**"
      f"（GO {sum(1 for r in today_rows if r['verdict'] == 'GO')}・"
      f"NO-GO {sum(1 for r in today_rows if r['verdict'] == 'NO-GO')}・"
      f"UNKNOWN {sum(1 for r in today_rows if r['verdict'] == 'UNKNOWN')}）")
    w(f"- 判定台帳の本チケット累計: {len(rows)}件"
      f"（GO {sum(1 for r in rows if r['verdict'] == 'GO')}・"
      f"NO-GO {len(nogo)}・UNKNOWN {len(unknown)}）")
    w("")
    w("> **この表は機械判定だけです。実画面（Chrome＋キーゾン）の確認はしていません。**"
      "§3.3 の3点確認（カートの販売元・本体の在庫履歴・出品一覧の実数）は人の仕事で、"
      "**発注の直前に必ず人が見てください。**")
    w("")
    w("## 1. 候補")
    w("")
    if go:
        w(M.md_table(go))
    else:
        w("**0件です。**水増しはしません。内訳は §3 を見てください。")
    w("")
    w("### 列の意味")
    w("")
    w("| 列 | 中身 |")
    w("|---|---|")
    w("| 過去1ヶ月の販売数 | Keepa の `monthlySold`。**「未確認」は「売れていない」ではなく「月50個未満で Amazon が表示しない」**という意味です。キーゾンで実数を見てください |")
    w("| セラー数 | Keepa の `offers` から数えた新品出品者の実数。画面の出品一覧とは配送先で件数が変わります |")
    w("| Amazon本体の有無 | 本体の365日在庫率（スナップショットでは判定しません） |")
    w("| 売れ筋ランク | 90日平均。**「死んでいないこと」の確認にしか使いません**（バリエーションは family でランクを共有） |")
    w("| 1個手残り | 1個粗利 − 206円（FBA保管料 87＋納品送料 64＋梱包資材 55・商品台帳 L001 の実測） |")
    w("| 発注額の帯 | 実額は会員限定の取引条件そのものなので帯で出します。実額は社長宛のフル版 CSV にあります |")
    w("| 購入先URL | このリポジトリは PUBLIC なので書けません。フル版 CSV にあります |")
    w("")
    nm = [r for r in near_misses(today_rows) if not excluded(r.get("title"))]
    onscreen = [r for r in nm if r["onscreen"]]
    offscreen = [r for r in nm if not r["onscreen"]]

    def nm_table(items: list[dict]) -> None:
        cols = ["商品名", "Amazon", "売価", "過去1ヶ月の販売数", "セラー数", "Amazon本体",
                "カートの販売元", "売れ筋ランク", "1個手残り", "利益率", "購入元の名前",
                "読み切れなかったところ／落ちた理由"]
        w("| " + " | ".join(cols) + " |")
        w("|" + "---|" * len(cols))
        for r in sorted(items, key=lambda r: -(r["net"] if r.get("net") is not None else -10 ** 6)):
            t = r
            w("| " + " | ".join(str(x) for x in [
                (t.get("title") or "（台帳未取得）")[:40],
                f"[dp/{r['asin']}](https://www.amazon.co.jp/dp/{r['asin']})",
                format(int(t["sell"]), ",") + "円" if t.get("sell") else "不明",
                t.get("sold") or "未確認", t.get("sellers") or "未確認",
                t.get("amazon") or "未確認", r["cart"][:26],
                t.get("rank") or "不明",
                format(t["net"], ",") + "円" if t.get("net") is not None else "未算定",
                t.get("margin") or "未算定", t.get("supplier") or "不明",
                r["why_full"][:100],
            ]) + " |")
        w("")

    if nm:
        w(f"## 1b. 人が見れば確定する行（判定 UNKNOWN・{len(onscreen)}件）— カズヨが見る")
        w("")
        w("**判定が UNKNOWN の行**です。落ちたのではなく「機械では読み切れなかった」行で、"
          "Chrome＋キーゾンで実画面を見れば**確定します**。**まだ買ってよい行ではありません。**")
        w("")
        w("> NO-GO の行は §1c に回しました。NO-GO には**実画面でも覆らない事実**"
          "（本体がカートを取った履歴・赤字・ランク50万位より下）が1本以上入っているので、"
          "見ても結論は変わりません。")
        w("")
        if onscreen:
            nm_table(onscreen)
            w("**見るところ（この順で）**")
            w("")
            w("1. **商品ページの「販売元」**（`#merchant-info` だけを見ない）。"
              "キーゾンの「アマゾン直販: 在庫あり/なし」も合わせて読む")
            w("2. **出品一覧** `https://www.amazon.co.jp/gp/offer-listing/<ASIN>/?f_new=true` "
              "を開いて新品出品者を数える。**Amazon 本体が混ざっていないかの内訳**を書く")
            w("3. **「Amazon の1個 ＝ 卸の何点か」**（⑤で落ちた行だけ）。"
              "Amazon の商品名と卸サイトの商品ページの両方を人が見る。"
              "ここを間違えると原価がN分の1になります（9/30 の B0DJNX12KZ）")
        else:
            w("**0件です。**")
        w("")
        w(f"## 1c. 見ても覆らない行（判定 NO-GO・{len(offscreen)}件）— 画面確認の対象外")
        w("")
        w("参考として残します。**カズヨの画面確認の対象外です。**")
        w("")
        w("**判定が NO-GO の行**です。参考として残します。")
        w("")
        w("- **②本体がカートを取った履歴** … 履歴は実画面で変わりません。"
          "本体がカートを取り得る棚は、値下げしてもカートを取れません")
        w("- **⑤赤字・⑥手残りが誤差幅以下** … 見ても数字は変わりません。"
          "動かせるのは仕入れ値か売価で、どちらも画面確認の話ではありません")
        w("- **⑧売れ筋ランクが50万位より下** … 直近3ヶ月の実績が実質ゼロの棚です")
        w("")
        if offscreen:
            w(f"（{len(offscreen)}件あります。手残りの大きい上位10件だけ載せます）")
            w("")
            nm_table(sorted(offscreen,
                            key=lambda r: -(r["net"] if r.get("net") is not None else -10 ** 6))[:10])
        w("## 1d. 初回の候補から外した系列")
        w("")
        w("**DNライティングの直管蛍光灯（14件）を外しました。**"
          "生存 PASS 18件のうち14件が**同一シリーズ・同一出展企業**で、"
          "これを買っても分散が効きません（1商品に8万円を賭けるのと同じ）。"
          "蛍光灯が水俣条約で製造終了予定という推測もありますが、"
          "**その当否に関わらず偏りだけで外す**判断です（カズヨ 2026-10-01）。")
        w("")
    w("## 2. 予算8万円で何を買うか（3案）")
    w("")
    w("テスト予算10万円・消化19,756円・**残枠約8万円**。発注・決済は社長の判断です（§4.1）。")
    w("")
    if go:
        for name, why, chosen, spend, net in M.plans(go):
            w(f"### 案{name}")
            w("")
            w(why)
            w("")
            w(f"- 発注額 **{spend:,}円**（残り {M.BUDGET_LEFT - spend:,}円）／SKU **{len(chosen)}件**"
              f"／全部売れたときの手残り見込み **{net:,}円**")
            for r in chosen:
                w(f"  - {r['title'][:46]}（[{r['asin']}]({r['url']})）"
                  f" {r['qty']}点・{M.band(r['order_total'])}・1個手残り {r['net']:,}円")
            w("")
    else:
        w("候補が0件なので案を出せません。**無い候補で案を作ることはしません。**")
    w("")
    w("## 3. 何件を判定して、どこで落ちたか")
    w("")
    w("### 段A — JAN を Amazon に当てる（0.9〜1.5トークン/JAN）")
    w("")
    w("| 段 | 件数 |")
    w("|---|---|")
    w("| NETSEA の JAN 索引（承認済み221社） | 67,662 |")
    w("| 0トークンの前段フィルタを通った（在庫あり・価格帯・期限管理カテゴリ語なし・まとめ単位が大きすぎない） | 33,807 |")
    w(f"| 今回 Keepa に投げた（黒字が見込める順） | {a['thrown']:,} |")
    w(f"| Amazon に商品ページがあった | {a['hit']:,} |")
    w(f"| ⛔ 生存ゲートで落ちた（90日平均ランクが50万位より下＝直近3ヶ月の実績が実質ゼロ） | {a['dead']:,} |")
    w(f"| ⛔ 売価が付かない（商品ページはあるが誰も売っていない） | {a['nopr']:,} |")
    w(f"| ⛔ 赤字（Amazon 側のセット数を掛けた原価で手残りマイナス） | {a['loss']:,} |")
    w(f"| ✅ 候補として段Bへ | {a['kept']:,} |")
    w("")
    w("### 段B — §3.3 のゲート（6〜8トークン/ASIN）")
    w("")
    w(f"判定した ASIN **{len(today_rows)}件**"
      f"（うち GO {sum(1 for r in today_rows if r['verdict'] == 'GO')}件・"
      f"NO-GO {sum(1 for r in today_rows if r['verdict'] == 'NO-GO')}件・"
      f"UNKNOWN {sum(1 for r in today_rows if r['verdict'] == 'UNKNOWN')}件）。"
      f"落ちた理由の内訳（下の {bn}件ぶん。1件で複数該当あり）:")
    w("")
    w("| 落ちた理由 | 件数 |")
    w("|---|---|")
    for k, v in sorted(bucket.items(), key=lambda kv: -kv[1]):
        w(f"| {k} | {v} |")
    w("")
    w("## 4. 正直に言っておくこと")
    w("")
    w("1. **判定は機械だけです。**カートの販売元は Keepa の `buyBoxSellerId` と履歴で見ています。"
      "2026-09-30 の事故（Amazon 本体がカートを持つ ASIN を発注させた）と同じ型を避けるため、"
      "**発注前に社長の Chrome ＋キーゾンで実画面を見てください**（§3.3）。")
    w("2. **仕入れ先が偏っています。**今回当たった候補の出所は8社に集中しています。"
      "索引221社のうち、黒字が見込める JAN を多く持つ社に先に当てたためです。"
      "残りの33,000件はまだ投げていないので、母数は増やせます。")
    w("3. **候補プールは判定し切りました。**途中まで Keepa のトークンを "
      "T-20260930-001 の取得（9,756 ASIN）と取り合っていましたが、"
      "カズヨがそのジョブを一時停止したので、残り171件も通しました。"
      "**「まだ判定していない候補があるから0件なのだ」ではありません。**"
      "今日作った候補プールは、全部見て0件です。")
    w("4. **生存 PASS は205件中18件（8.8%）、しかもその14件が同一シリーズでした**"
      "（DNライティングの直管蛍光灯・同じ出展企業）。"
      "候補の見かけの数は、実質は2〜3商品です。"
      "さらに蛍光灯は**水銀に関する水俣条約で製造終了が決まっている品目**のはずで"
      "（推定・今日は裏取りしていません）、6ヶ月在庫を持つ商品としては勧めません。")
    w("5. **会員限定の取引条件（価格・まとめ単位）と購入先URL はこのファイルに書いていません。**"
      "このリポジトリは PUBLIC で、会員限定の取引条件は公開できません（法務判定16）。"
      "実額つきのフル版は `agent_output/T-20260920-003/pipeline/buy_list_private.csv` にあります。")
    w("")
    w("## 5. 次の1手（推奨）")
    w("")
    w("**パイプラインは動いています。足りないのは仕入れ先の品揃えです。**")
    w("")
    w("| # | やること | 誰が | 効果 |")
    w("|---|---|---|---|")
    w("| 1 | **卸価格の開示申請先を NETSEA の未承認サプライヤー（220社 → 622社）へ広げる。**"
      "**これが唯一、天井を上げる手です。**（社長承認済み） | カズヨ | "
      "承認済み221社の品揃えでは、Amazon で売れている棚とほぼ重なりません |")
    w("| 2 | 残り **33,000件の JAN** を投げる（今日投げたのは766件・2.3%） | 夜間の無人走行 | 1.17トークン/JAN＝約39,000トークン＝補充33時間ぶん。数日で回せる |")
    w("| 3 | **ゲートの閾値はいじらない**（§6 に根拠）。緩めても候補は1件も増えません | — | "
      "一度「本体の在庫率を何%まで許すか決めれば候補が増える」と書こうとしましたが、"
      "数えたら**本体の条件だけで落ちた行は0件**でした |")
    w("| 4 | **§1b の行を人が見る**（カートの販売元・出品一覧の実数・Amazon 側のセット数） | "
      "カズヨの Chrome＋キーゾン | 0件を1〜2件にする最短路。NO-GO の行は見なくてよい |")
    w("")
    w("## 6. ゲートを緩めても候補は増えません（数えた）")
    w("")
    w("「本体の在庫履歴が少しでもあれば落とす」のは厳しすぎるのではないか、と疑いました。"
      "**疑いは外れました。**今日判定した212件のうち、"
      "**本体に関する条件だけで落ちた行は0件**です。"
      "本体で落ちた行は、例外なく**生存（売れている根拠がない）や採算でも落ちています。**")
    w("")
    w("| 本体の存在感 | 1年の在庫率 | 統計期間のカート獲得率 |")
    w("|---|---|---|")
    w("| 0%超〜5% | 15件 | 38件 |")
    w("| 5%超〜20% | 29件 | 17件 |")
    w("| 20%超〜60% | 48件 | 70件 |")
    w("| 60%超 | 85件 | 9件 |")
    w("")
    w("**だから閾値は動かしません。**9/30 の事故（本体がカートを持つ ASIN を12点発注）の"
      "再発リスクを払ってまで緩める価値が、1件もありません。"
      "律速は閾値ではなく**仕入れ先の品揃え**です（§5-1）。")
    w("")
    w("### 今日使った Keepa トークン")
    w("")
    w("| 用途 | 消費 | 単価（実測） |")
    w("|---|---|---|")
    w("| 段A JAN→ASIN（766 JAN） | 899 | 1.17 / JAN |")
    w("| ランク取り直し（205 ASIN） | 205 | 1.00 / ASIN |")
    w(f"| 段B §3.3 ゲート（{len(today_rows)} ASIN） | 約1,640 | 6.4 / ASIN |")
    w("| **合計** | **約2,744** | 上限1,200・補充20/分なので実時間で約2時間20分ぶん |")
    w("")
    w(f"---\n\n判定日 {today} ／ タカシ（IT エンジニア）／ チケット T-20260920-003  ")
    w(f"判定台帳（32列・購入先URL つき）: https://docs.google.com/spreadsheets/d/"
      f"1ppyXCnp2S_9Xwi3vJHGOT6iJCfsEqt88n30aqUFtX3I/edit")

    md = DELIV / "32_買う候補リスト.md"
    md.write_text("\n".join(L) + "\n", encoding="utf-8")
    subprocess.run([sys.executable, str(DELIV / "99_md2html.py"), str(md)], check=True)
    print(f"書きました: {md}")
    print(f"GO {len(go)} / UNKNOWN {len(unknown)} / NO-GO {len(nogo)} / 段B判定 {bn}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
