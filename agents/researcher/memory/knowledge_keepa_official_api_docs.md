# Keepa 公式一次情報の所在と、用語定義の決着（T-20260824-001）

- **記録日**: 2026-08-24 / **記録者**: サトル（リサーチャー）
- **成果物**: `workspace/output/deliverables/T-20260824-001/`
- **種類**: 一次情報の所在＋用語定義（今後 Keepa を調べる全員の起点）

## 結論（次に Keepa を調べる人が最初に読む3行）

1. **Keepa に公式のユーザーマニュアルは存在しない。**`keepa.com/help` `/faq` `/manual` `/guide` `/docs` `/tutorial` `/sitemap.xml` は**全部404**（2026-08-24 実測）。探すな。
2. **唯一の厳密な一次情報は `https://keepa.com/api-docs/` の英語APIリファレンス30ページ。静的HTMLなので curl / WebFetch で全文取れる。**`product-object.html` `statistics-object.html` `seller-object.html` `product-finder.html` `changelog.html` の5本が本丸。
3. **keepa.com 本体は WebSocket 駆動のSPA**（`wss://push.keepa.com/`）。`#!` はサーバに送られないので**URLを変えても同じ9,111バイトの空シェルが返る**。機械取得は不可能 → カズヨにブラウザ実機を頼む。

## 日本語UIラベルの原語を確定させる公式手段（最重要の技）

**Product Finder の公式ドキュメント末尾に明記**：「Keepaサイトの Product Finder で条件を組み、結果表の上の **"Show API query"** をクリックすると、その条件の API クエリ（＝フィールド名）が読める」。
→ **推測なしで日本語UI ⇄ API原語を1回で全部確定できる。**次に誰かが「このラベルの意味は？」と聞いてきたら、まずこれ。

## 決着させた用語（当社が長く「要確認」で放置していたもの）

| 日本語UI | 実体（公式） | 教訓 |
|---|---|---|
| **BUY BOX の平均売上数** | `avgBuyBoxCompetitors` ＝ **Buy Box を争う平均競合出品者数（自分を含む）** | **売上ではない。日本語UIは正反対の誤訳。**Keepaの日本語は機械翻訳。ラベルを信じるな |
| **購入ボックス切り替えの所有者** | `buyBoxNewOwnershipRate` ＝ 新品Buy Box平均獲得率(%) | 当社の推定が正しかった。**「推測」と明記して残しておいたから、後で答え合わせができた** |
| **ボックスを購入する 中古の所有者** | `buyBoxUsedOwnershipRate` ＝ 中古Buy Box平均獲得率(%) | 同上 |
| **え**（96%） | `positiveRating` ＝ **★4または★5の比率** | 「高評価率」で概ね合っていたが、定義（★4以上）は取れていなかった |
| **評価 -1%** | ❓公式定義なし。`buyBoxStats` に評価項目は存在しない | **不明のまま確定させた。**推測で埋めない |

## 手口として再利用できること

- **UI のラベルが読めないときは、対応する API フィールドの定義から逆算する。**値の型が手がかりになる：8.83（小数2桁）→ Float 型は Seller Object に `avgBuyBoxCompetitors` ただ1つ。4%/1%（整数%）→ Integer の ownershipRate 2つ。**型と値の形で候補を1つに絞れる。**
- **`changelog.html` を必ず見る。**当社ナレッジの腐り具合が一発で分かる。今回 2026-02-23 の「NEW/USED の価格定義が listing price → landing price に変わった」を発見。**同じ列名のまま意味が変わる**のが一番怖い。
- **公式ドキュメント同士でも矛盾する。**Domain ID は Product Request が12(com.br)まで、Seller Object は11まで。ベストセラー件数は best-sellers.html が「ルート50万」、plans-tokens.html が「最大10万」。**どちらが正しいとは書かない。矛盾を矛盾として報告する。**
- **GitHub org `keepacom`（api_backend / php_api）は公式の実装＝定義の裏取りに使える。**Python クライアント `akaszynski/keepa` は**コミュニティ製で公式ではない**（公式が自分でそう書いている）。

## 到達できなかったこと（次の人へ）

- keepa.com の商品ページは **Anti-bot check** が出て実機でも遷移できない（カズヨ確認）。**回避は禁止。**グラフ凡例の英語ラベルは、Chrome拡張側（Amazon商品ページ上）で言語を English にして読むのが唯一の手。
- 公式ブログは**未発見**（「無い」とは断定していない）。
- 公式YouTube `@KeepaTutorials` は存在するが、keepa.com からリンクされているかは未確認。動画一覧はJS描画で機械取得不可。
