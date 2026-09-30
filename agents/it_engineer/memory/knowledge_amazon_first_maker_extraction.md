# Amazon 起点のメーカー抽出（本書3基準＋積極条件）— 実測と手順（T-20260930-001 / 2026-09-30）

「Amazon で売れている商品 → 国内中小メーカー」の候補を Keepa で出す型。**次に同じ依頼が来たら、
`deliverables/T-20260930-001/` の 10_funnel.py → 20_fetch.py → 30_build.py をそのまま回す。**

## Finder で効くフィールド（domain=5・件数が動くことで実測確認）

| フィールド | 効き | メモ |
|---|---|---|
| `monthlySold_gte` | 有効（2.09億→43.5万） | 積極条件はここで入口に置ける |
| `offerCountFBA_gte` | 有効（41.4万→5.34万） | 既知 |
| `buyBoxIsFBA: true` | 有効 | |
| `buyBoxIsUnqualified: false` | FBA=true の後では件数不変。**True 側で 1,728 件出る＝フィールドは効いている** | Boolean は逆側でも確かめる |
| `buyBoxIsAmazon: false` | 有効（1.98万→1.31万） | スナップショット。前段の絞りとしてだけ使う |
| `buyBoxStatsAmazon365_lte: 10` | 有効（1.31万→9,756） | 「本体365日在庫切れ≥90%」の必要条件。**Finder に outOfStockPercentage365 は無い（90 だけ）** |
| `categories_exclude`（ルートID） | 有効 | |

**ルートカテゴリ ID は /category で取ったものを使う。** 他セッションの `product_finder.py`（T-20260920-003/26_）は
ミュージック 562002（正 561956）・ソフト 637394（これはゲーム。PCソフトは 637392）・ビューティー 161669011（正 52374051）と誤っていた。

## product の読み方

- **`buybox=1` は 3 token/ASIN（通常 1）。** 付けると `stats.buyBoxSellerId` が埋まる。**代表 ASIN だけに使う。**
- offers なしでは `stats.offerCountFBA=-2`。**`stats.current[34]`＝FBA 数・`[35]`＝FBM 数**（Finder の FBA≥2 と 99% 一致で確認）
- 本体の在庫切れ率＝`stats.outOfStockPercentage365[0]`（Amazon 列）。**-1 は本体の価格データ無し＝100% 扱い**
- Finder で BB 統計の前段を掛けても、product 側 oos365≥90 で **2,500→2,275（9%落ち）**。後段判定は省略できない

## 漏斗（2026-09-30 実測）

2.65億 → ルート除外 2.09億 → monthlySold≥50 43.5万 → ランク≤5万 41.4万 → FBA≥2 5.34万 → カートFBA 4.11万
→ 売価≥2,200 1.98万 → カート非Amazon 1.31万 → 365日BB非Amazon 9,756（うち A 条件 2,463）。
**A 2,500 ASIN の取得（2,500 token・約2時間）でメーカー 1,140 → 一次除外後 339社（うち本人カート疑い92）。** 100社目標は A だけで足りる。

## 一次除外で漏れる型（目視で見つけた）

1. **カタカナ表記の海外ブランド**（タイトリスト・イソップ・シャネル）は T-1 の `segment()` を「国内」で通る。
   → **JAN が 45/49 でなく、manufacturer に日本の法人格が無ければ「海外ブランド疑い」**で外す（公開版に理由つきで残す）
2. **上場・大手の化粧品/製薬/家電**は既知リストに無いと残る（参天・MTG・リコー・ミルボン系）。`maker_rules.EXTRA_BIG` に足した
3. 逆に **国内の英字ブランド（BURTLE）は「中国系OEM疑い」に落ちる**。過去台帳（T-20260831-004）で「連絡候補」の社は機械区分より優先して残す
4. 「非公開」「LEACCO公式店」のように manufacturer が社名でない行がある

## 設計の要点

- raw は agent_output に gzip、**`--from-raw` で 0 token 再計算**。ルールを直すたびに Keepa を叩かない
- 取得順は「A 条件の一覧 → 残り」で固定し order.json に保存（バッチ番号がずれない）
- buybox 取得は ASIN 単位のキャッシュ（代表 ASIN が再計算で入れ替わるため）
- 公開版 CSV は A クラス列だけ（在庫切れ率・90日比・実セラー数は完全版にだけ）

関連: [[knowledge_counting_makers_under_token_cap]] [[knowledge_keepa_product_finder_fields]] [[knowledge_company_size_gate_design]]

## 自分で踏んだ罠（2つ）

- **「過去台帳で連絡候補なら残す」救済を、大手判定より前に置いた。** サンワダイレクト・Wizards of the Coast が台帳の「連絡候補」で救われて残った。救済は**区分（海外/OEM疑い）の除外だけを打ち消す**。大手判定は救済の後でも必ず当てる
- **manufacturer に商品説明が入る行では、説明中の他社名で大手判定される。** 「マタインク for キヤノン用インク…」がキヤノンで除外された。`DESC`（for/対応/互換…）に当たる manufacturer は判定に使わない
- 背景で待つとき `pgrep -f "30_build.py --bb"` は**自分の until ループの文字列にも当たって**永遠に終わらない。PID を控えて `kill -0 <pid>` で待つ
