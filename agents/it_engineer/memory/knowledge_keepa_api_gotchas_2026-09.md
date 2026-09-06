# Keepa API を直接叩くときの実務メモ

T-20260906-002 / 2026-09-06。既存の `adapters/keepa.py` はスタブのままなので、
毎回同じところで詰まらないように残す。

## 詰まった順に

1. **レスポンスは gzip だが `Content-Encoding` ヘッダが付かないことがある。**
   `json.load(resp)` が `UnicodeDecodeError: 0x8b` で落ちる。
   **マジックバイト `\x1f\x8b` で判定して `gzip.decompress` する**のが確実。
2. **Product Finder の `perPage` は最小 50。** 小さい値だと
   `combination of perPage and page exeeds limit or is too small`（原文ママ・typo あり）で HTTP 400。
   `sort` やカテゴリ条件のせいだと誤診しやすい。
3. **カテゴリ ID は推測しない。** JP の文房具・オフィス用品は `86731051`。
   `86727051` や `2016926051` は**エラーにならず 0 件を返す**ので、条件の書き方を疑って
   トークンを溶かすことになる。ルート一覧は `/category?category=0&parents=0`（1 token）で取れる。
   JP のルートは 31 個しかない。
4. **`categories_include` ではなく `rootCategory`** を使う（ルートで絞るとき）。
5. **`COUNT_REVIEWS` / `RATING` は `offers` か `rating` を付けないと埋まらない。**
   300 件取って 0 件しか埋まらなかった。既知の罠だが、実際に踏むまで実感が湧かない。
   **`offers` を付けると 1 ASIN あたり 1 → 7 token。** 全件走査には使えない。
6. **`monthlySold` と `salesRankDrops*` は `offers` なしで取れる**（1 token/ASIN）。
   母数を広く取る調査はこちらだけで組む。

## トークン設計の目安（2026-09 時点の契約）

- 回復 20/分（≒1,200/時）、残高上限は数千。
- Product Finder = 10 token/query（何件返っても同じ）
- product = 1 token/ASIN（`offers` 付きで 7）、1リクエスト最大 100 ASIN
- **層化抽出 6帯 × 50件 ≒ 360 token（約20分ぶん）。** 調査設計はこの単位で見積もる。

## 分析の作法

**生レスポンスをリポジトリに残さない**（PUBLIC・Keepa T&C §11(1)）。
`agent_output/` に置いて集計だけ `deliverables/` に出す。
成果物に書いてよいのは分布・相関・閾値・手法で、**個別 ASIN の行データは不可**。
