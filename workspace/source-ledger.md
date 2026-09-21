# 出所台帳 — その情報はどこから来たか

**目的**：取引条件（卸値・上代・ロット・送料・手数料）を成果物に書くとき、**出所が会員限定か公開ページか**を機械が判定できるようにする。
2026-09-21、SD 会員限定の取引条件が 3チケット・15ファイルに広がって push された事故を受けて新設（`.claude/hooks/source-terms-guard.py` が本ファイルを参照して書き込みを止める）。

**運用**：新しい仕入れ先・API・データ源を使い始めたら、その turn 内でここに1行足す。責務は庶務マリエ。`SOURCE:` 行が機械可読部で、フックはこの行だけを読む。

**書式**：`SOURCE: <ホスト名またはサービス名> | <区分> | <禁止の型> | <根拠条文> | <確認日>`
- 区分は **`会員限定`** か **`公開`** のいずれかで始める（フックはこの2語だけを見る）。
- `公開` 区分は、法務の「公開ページ由来ルール」4条件をすべて満たしたものだけ載せる。
  1. 非ログインで表示されることを**取得当日に実測**した
  2. 出典 URL と取得日を成果物に併記する
  3. 出典サイトの規約に**発信・転載・秘密保持の禁止条項がない**ことを全文検索で確認した
  4. **出所が会員制卸（SD・NETSEA 等）ではない**
- `公開` 区分に載っているホストは、成果物中に
  `<!-- public-source: https://<ホスト>/... verified:YYYY-MM-DD -->`
  を金額の直前3行以内に書けば、フックが止めなくなります。**これが唯一の出口です。**

**PUBLIC リポジトリです。** ここに実額・品番・会員 ID は書かない。書くのは「どの出所が何区分か」だけ。

---

## 機械可読部（この形式を崩さないこと）

SOURCE: スーパーデリバリー | 会員限定 | 一般的発信禁止型 | 会員規約 17条1項 | 2026-09-20
SOURCE: superdelivery.com | 会員限定 | 一般的発信禁止型 | 会員規約 17条1項 | 2026-09-21
SOURCE: NETSEA | 会員限定 | 秘密保持型（金額のみ） | API利用規約 15条1項 / 会員規約 7条2項3号 | 2026-09-06
SOURCE: netsea.jp | 会員限定 | 秘密保持型（金額のみ） | API利用規約 15条1項 | 2026-09-21
SOURCE: api.netsea.jp | 会員限定 | API応答は全項目 | API利用規約 15条1項 | 2026-09-21

SOURCE: fuwamarket-b2b.com | 公開 | 発信禁止条項なし・robots Allow（policy crawlable と明記） | https://fuwamarket-b2b.com/policies/terms-of-service | 2026-09-21
SOURCE: www.ornedefeuilles.com | 公開 | 発信禁止条項なし・robots Allow・canonical あり | https://www.ornedefeuilles.com/pages/stockists-guide | 2026-09-21
SOURCE: www.moon-rabbit.jp | 公開 | 発信禁止条項なし・当該パスに Disallow なし | https://www.moon-rabbit.jp/c-fpage?fp=wholesale | 2026-09-21
SOURCE: www.toyoake.or.jp | 公開 | 発信禁止条項なし・Disallow は管理画面のみ | https://www.toyoake.or.jp/guide/distributor-new-transaction/ | 2026-09-21
SOURCE: 117kirei.com | 公開 | 発信禁止条項なし・Disallow は管理画面のみ | https://117kirei.com/2025sinkidauruten/ | 2026-09-21
SOURCE: daikichikimchi.jp | 公開 | 発信禁止条項なし・Disallow は管理画面のみ・Sitemap 公示 | https://daikichikimchi.jp/kimchi/wholesale/ | 2026-09-21

<!--
上記6件は法務ハルオが 2026-09-21 に**3本足（非ログイン表示の実測・robots・ToS の禁止語全文検索）**で
確認したもの。判定の詳細は法務判定 16 §8-2（commit 857e0f06）。出所はすべて
T-20260903-001/research/raw/02_primary_disclosure.md に一次開示として収録された供給側。

注意3点:
1. **www.ornedefeuilles.com** は ToS 検索で `発信` が1件当たるが、**通知の到達時期を定めた条項
   （発信主義）**であって情報発信の禁止ではない、というのがハルオの判定。他の禁止語は0件。
2. **www.superdelivery.com は「公開」区分に入れない。** 非ログインで読める自社ページ由来の比率が
   S1・S2 にあるが、**会員規約17条1項に公知除外がない**ため会員限定のまま（判定16 §8-3）。
   **ガードが SD 由来の金額を止めるのは誤検知ではなく正しい挙動。**既に 01_*.html 238行に入っている
   分は取り下げ不要（SD 自身が広告として掲げる自社統計）で、措置は「これ以上増やさない」。
3. `daikichikimchi.jp` は raw/02 側の「本文確認」が未（検索結果のハイライトのみ）だが、
   ハルオが 2026-09-21 に非ログイン200 を自ら実測して公開可と判定している。

**経緯**：当初この区分は空で、判定16 §2 が行番号で名指ししていたのが1ホストだけだったため、
庶務は1件のみ登録して残りを差し戻した。原因はハルオの検索語が `20,000円以上` 固定で、2件目の
`20,000円（税込22,000円）未満` を拾えなかったこと（**§5 で自分が指摘した表記ゆれを §2 に適用して
いなかった**）。**「当てはまりそうで足さない」を守ったことで、誤ったホストを登録せずに済んだ。**
-->---

## 根拠

- `workspace/output/deliverables/T-20260920-003/16_公開リポに残る取引条件の公開可否_法務判定.md` §5 対策1
- `agents/legal/memory/knowledge_public_page_terms_rule_and_leak_detection.md` §1
