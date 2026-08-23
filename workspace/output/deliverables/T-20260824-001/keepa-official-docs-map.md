# Keepa 公式ドキュメント 所在マップ

- チケット: T-20260824-001 ／ 調査: サトル（リサーチャー）
- **全件の最終確認日: 2026-08-24**（Keepa は 2026-02 / 2026-03 / 2026-04 / 2026-07 / 2026-08 と立て続けに仕様変更しています。**3ヶ月経ったら再確認してください**）

---

## 結論（イシューへの答え）

**イシュー：「Keepa に公式の説明書は存在するのか。存在するならどこか」**

| 問い | 答え | 確度 |
|---|---|---|
| 公式の **API リファレンス** は存在するか | **存在する。`https://keepa.com/api-docs/` 配下に静的HTMLで30ページ**。全フィールドに型と定義が付いた、Keepa で最も厳密な一次情報 | **事実**（全30ページを HTTP 200 で取得済み） |
| 公式の **ユーザー向け操作マニュアル**（拡張機能・グラフの読み方）は存在するか | **専用の説明書ページは存在しない。** `keepa.com/help`, `/faq`, `/manual`, `/guide`, `/docs`, `/tutorial` はすべて **404**。`sitemap.xml` も 404。存在するのは SPA 内の `#!support`（FAQ）と `#!features`（機能一覧）のみ | **事実**（7パス＋sitemap を curl で確認） |
| 用語の定義を確定させる一次情報はどこか | **API ドキュメント一択。** UI 側には用語集がない。**日本語UIの怪しいラベルは、対応する API フィールドの定義から逆算するのが唯一の確実な方法** | 事実＋当社の運用判断 |

> **重要な副産物：** Product Finder の公式ドキュメントに「**Keepa サイトの Product Finder で条件を組み、結果表の上にある "Show API query" をクリックすると、その条件の API クエリ（＝フィールド名）が読める**」と明記されています（`product-finder.html` 末尾 Tip）。これが**日本語UIラベル ⇄ API原語の対応を、推測なしで確定させる公式の手段**です。カズヨへの実機依頼リストの筆頭に置きました。

---

## 1. 公式APIドキュメント（静的HTML・WebFetch/curl で全文取得可）

すべて `https://keepa.com/api-docs/` 配下。言語は**英語のみ**（日本語版なし）。2026-08-24 に全ページ HTTP 200 で取得し、`workspace/output/agent_output/T-20260824-001/sources/` に保存済み。

### Getting Started

| URL | カバー範囲 | 当社にとっての重要度 |
|---|---|---|
| `https://keepa.com/api-docs/` | 概要・クイックスタート・エンドポイント一覧 | 中 |
| `https://keepa.com/api-docs/request-basics.html` | ベースURL・キー・gzip必須・レスポンス封筒（tokensLeft等）・HTTPステータス | 中 |
| `https://keepa.com/api-docs/plans-tokens.html` | **トークンバケット方式の公式定義**・料金と課金・リクエスト種別ごとのトークン単価 | 高 |
| `https://keepa.com/api-docs/changelog.html` | **仕様変更履歴（最新 2026-08-18）**。当社ナレッジの腐り具合を測る唯一の公式ソース | **最高** |
| `https://keepa.com/api-docs/mcp.html` | **公式 MCP サーバ**（`https://keepa.com/mcp`）。AIアシスタントに Keepa を直結する公式手段 | 高（後述） |

### Response Objects（用語定義の本丸）

| URL | カバー範囲 | 重要度 |
|---|---|---|
| `https://keepa.com/api-docs/product-object.html` | **Product Object 全フィールド定義＋csv履歴配列の全36インデックス＋Keepa Time 換算** | **最高** |
| `https://keepa.com/api-docs/statistics-object.html` | **stats オブジェクト全フィールド。Buy Box 統計・salesRankDrops・出品数** | **最高** |
| `https://keepa.com/api-docs/offer-object.html` | 個別オファー（出品）1件の定義。condition コード表 | 高 |
| `https://keepa.com/api-docs/seller-object.html` | **出品者オブジェクト。当社の未確定3ラベルはここで全部解決した** | **最高** |
| `https://keepa.com/api-docs/deal-object.html` | セール（取引）オブジェクト | 低 |
| `https://keepa.com/api-docs/category-object.html` | カテゴリノード | 中 |
| `https://keepa.com/api-docs/best-sellers-object.html` | ベストセラーリスト | 中 |
| `https://keepa.com/api-docs/notification-object.html` / `tracking-object.html` / `tracking-creation-object.html` | トラッキング・通知 | 低 |
| `https://keepa.com/api-docs/lightning-deal-object.html` / `search-insights-object.html` | タイムセール／検索インサイト | 低 |

### Endpoints

| URL | カバー範囲 | 重要度 |
|---|---|---|
| `https://keepa.com/api-docs/product.html` | **Product Request の全パラメータ（stats / offers / buybox / rating / stock / days / history / update）とトークン単価** | **最高** |
| `https://keepa.com/api-docs/product-finder.html` | **Product Finder の全フィルタ名と定義。「下落(delta)」の符号仕様もここ** | **最高** |
| `https://keepa.com/api-docs/seller.html` / `seller-finder.html` / `most-rated-sellers.html` | 出品者情報／出品者ファインダー（2026-08-09 新設）／高評価セラー | 中 |
| `https://keepa.com/api-docs/deals.html` | 取引（値下がり）検索 | 中 |
| `https://keepa.com/api-docs/best-sellers.html` | ベストセラーリスト取得 | 中 |
| `https://keepa.com/api-docs/category-lookup.html` / `category-search.html` | カテゴリ検索 | 中 |
| `https://keepa.com/api-docs/product-search.html` | キーワード検索 | 中 |
| `https://keepa.com/api-docs/graph-image.html` | **グラフ画像API。Keepaのグラフが「3種類」であることの公式定義がここ** | 高 |
| `https://keepa.com/api-docs/tracking.html` | トラッキング管理 | 低 |

---

## 2. keepa.com 本体（SPA・機械取得不可）

**事実：** `https://keepa.com/` が返すのは 9,111 バイトのローダー用シェルHTMLのみで、本文は**WebSocket（`wss://push.keepa.com/`）経由で描画**されます。`#!` フラグメントはサーバに送られないため、**`#!support` も `#!features` も、URL が違っても curl / WebFetch には同じ空シェルが返ります**（`#!api` で実測確認）。

| URL | 中身 | 機械取得 | 誰が見るか |
|---|---|---|---|
| `https://keepa.com/#!support` | 公式FAQ（はじめに／拡張機能・グラフ／トラッキングと通知／請求とアカウント） | ✗ | **カズヨ（実機）** |
| `https://keepa.com/#!features` | 「サイトの機能」＝公式ユーザーマニュアルに最も近いページ | ✗ | **カズヨ（実機）** |
| `https://keepa.com/#!news` | アップデート告知 | ✗ | カズヨ |
| `https://keepa.com/#!finder` / `#!viewer` / `#!bestseller` / `#!topseller` / `#!sellerlookup` / `#!categorytree` | Pro 6ツール | ✗ | **カズヨ（実機）** |
| `https://keepa.com/#!api` | APIプラン・キー・トークン残量 | ✗ | 社長のみ（要ログイン） |
| `https://keepa.com/#!disclaimer` | 法的情報・プライバシー | ✗ | 必要時 |

**存在しないもの（404 を実測。「探せば見つかる」ではなく「無い」と確定させます）**
`keepa.com/help` / `/faq` / `/support` / `/tutorial` / `/docs` / `/guide` / `/manual` / `/sitemap.xml` / `/api.html`

**robots.txt**（2026-08-24 取得）：`Disallow: /r/`, `/ajax/`, `/refererControlDisqus.html` のみ。api-docs はクロール許可。

---

## 3. 公式コード（一次情報として使える。フィールド定義の裏取りに有効）

| 名称 | URL | 中身 | 最終push |
|---|---|---|---|
| Keepa 公式 Java クライアント | `https://github.com/keepacom/api_backend` | Product / Offer / Stats のモデルクラス（実装がそのまま定義） | 2026-07-25 |
| Keepa 公式 PHP クライアント | `https://github.com/keepacom/php_api` | 同上 | 2026-07-04 |
| Python クライアント | `https://github.com/akaszynski/keepa` | **コミュニティ製（公式ではない）**。api-docs から「community-developed」と明示リンクされている | — |

> GitHub organization `keepacom` に**公開リポジトリは上記2本のみ**（GitHub Search API で確認・2026-08-24）。

---

## 4. 公式フォーラム／YouTube／ブログ

| 対象 | 状態 | 備考 |
|---|---|---|
| 公式フォーラム | **`discuss.keepa.com` は DNS 解決せず（存在しない）。** keepa.com 内の `#!discuss` 系はSPA配下 | 旧来「Keepa の API ドキュメントはフォーラムに置かれている」という理解がありましたが、**2026-08 時点では独立した `api-docs/` に移行済み**です |
| 公式YouTube | `https://www.youtube.com/@KeepaTutorials`（旧ID `UCVRSi_d8d48o6Ooa-ujKaWw`）。チャンネル説明に keepa.com へのリンクあり | **「keepa.com 側からこのチャンネルへリンクされているか」は未確認。** 動画一覧はJS描画で機械取得不可 → カズヨへ依頼 |
| 公式ブログ | **発見できず**（api-docs 内・keepa.com シェルHTML 内ともにリンクなし） | 「無い」と断定はしません。未発見です |
| 公式サポート窓口 | `info@keepa.com`（api-docs 内に明記） | §4.1 該当（第三者連絡）。問い合わせは社長承認が必要 |

---

## 5. カズヨへ：ブラウザ実機で見てほしいURL（優先順）

| # | URL | 見てほしいもの | なぜ必要か |
|---|---|---|---|
| 1 | `https://keepa.com/#!finder` | 条件を1つ設定 →結果表の上の **「Show API query」**（日本語では別表記の可能性）をクリックし、**表示されたJSONのフィールド名**をそのままコピーしてください。特に**「下落」欄**と**日本語ラベルの全項目**（左のフィルタ一覧）のスクショ | **これが日本語UI ⇄ API原語を推測なしで確定させる公式手段**です（公式Tipに明記）。1回で Product Finder の全ラベルが確定します |
| 2 | `https://keepa.com/#!sellerlookup` → 任意の出品者 | 「パフォーマンス」欄の**8項目を、表示言語 日本語 と English で1枚ずつ**スクショ | 未確定3ラベルは API 定義から逆算で決着済み（本書 glossary 参照）ですが、**英語原語ラベルの実物**が取れれば確度が「推測（高）」から「事実」に上がります |
| 3 | `https://keepa.com/#!support` | FAQ 全設問を展開したスクショ（特に「価格データの信頼性はどの程度ですか？」「どのくらいの頻度でデータ更新していますか？」） | データ鮮度の公式見解。当社の「Keepaの数字をどこまで信じるか」の根拠になる |
| 4 | `https://keepa.com/#!features` | 全文 | 唯一の公式ユーザーマニュアル相当 |
| 5 | 商品ページの Keepa Box → 設定タブ | 画面右上「言語」を English に切り替えた状態の**グラフ凡例**と**Dataタブ4サブタブ**のスクショ | §1〜§3 の日本語ラベルの原語確定（本書では csv type から推定済み・要裏取り） |
| 6 | `https://keepa.com/#!api` （要ログイン・社長のみ） | **現在の請求額（€19 か €29 か）** と **トークン生成レート** | T-20260817-004 から持ち越しの未確認事項。§4.1 の課金には触れず、閲覧のみ |
| 7 | `https://www.youtube.com/@KeepaTutorials` | 動画本数・最新投稿日・keepa.com からのリンク有無 | 公式かどうかの裏取り |

---

## 6. 打ち切り条件（宣言どおり）

- 宣言した3条件（①所在確定 ②Product object 全フィールド取得 ③未確定3ラベルの決着）をすべて満たしたため、ここで探索を打ち切りました。
- **これ以上は推測になるライン**：SPA 内の画面文言、公式ブログの有無、YouTube の内容。いずれも**ブラウザ実機でしか確認できない**ため、上表としてカズヨへ引き渡します。
