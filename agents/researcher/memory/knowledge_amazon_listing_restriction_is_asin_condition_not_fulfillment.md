---
name: knowledge-amazon-listing-restriction-is-asin-condition-not-fulfillment
description: Amazonの出品制限は ASIN × マーケットプレイス × コンディション で決まり、FBA/出品者出荷は判定要素に入らない。Amazon公式SP-APIモデルで構造的に確認（2026-10-09）。NOT_ELIGIBLE は解除経路が存在しない制限
metadata:
  type: knowledge
---

# 出品制限の判定軸は「ASIN × コンディション」。配送方法は入らない

**イシュー**：「FBA では出品が消されたが、出品者出荷（FBM）なら出せるのではないか」— **出せない。**

## 一次情報（Amazon公式のデータモデル）

`amzn/selling-partner-api-models` の `models/listings-restrictions-api-model/listingsRestrictions_2021-08-01.json`
（取得 2026-10-09 / raw.githubusercontent.com 経由で誰でも取得可・ログイン不要）

**`GET /listings/2021-08-01/restrictions` のリクエストパラメータは6つだけ**
`asin`（必須）／`conditionType`／`sellerId`（必須）／`marketplaceIds`（必須）／`reasonLocale`／`productType`
→ **FBA か出品者出荷かを指定するパラメータが存在しない。**

**`Restriction` オブジェクトの修飾子は `marketplaceId` と `conditionType` の2つだけ**
`conditionType` enum（13種）：`new_new` `new_open_box` `new_oem` `refurbished_refurbished` `used_like_new` `used_very_good` `used_good` `used_acceptable` `collectible_like_new` `collectible_very_good` `collectible_good` `collectible_acceptable` `club_club`
→ ここにも配送方法の次元が無い。

**`reasonCode` enum は3種だけ**

| reasonCode | 意味 | 当社の扱い |
|---|---|---|
| `APPROVAL_REQUIRED` | 承認が必要。**解除経路（path forward link）が提供される** | ブランドゲート等。書類で開く（CLAUDE.md §3.5 #1〜#3） |
| `ASIN_NOT_FOUND` | 指定ASINがそのマーケットプレイスに存在しない | — |
| 🔴 `NOT_ELIGIBLE` | 「出品を作成する資格がない。**解除する path forward link は提供されない**」 | **諦めるしかない。書類も申請も意味がない** |

## 実機の文言との対応

セラーセントラルで「**現在、この商品の新しい出品情報は受け付けておりません**」＋「出品を申請」ボタンがグレー ＝ **`NOT_ELIGIBLE`**。
`/hz/approvalrequest/restrictions/approve?asin=<ASIN>&itemcondition=New` という URL 自体が **asin と itemcondition の2変数しか取らない**ことも同じ構造を示す。
拒否理由も「その他の商品／**再生品のコンディション**の〜カテゴリー／**コレクター商品のコンディション**の〜カテゴリー」と、**カテゴリー × コンディション**で列挙される。

## 実例（2026-10-09・社長宅在庫12点）

和平フレイズ 燕三 よせしゃぶ鍋22cm EM-103（B0FVL8QST6）
- ブランドゲート（`APPROVAL_REQUIRED`）は 10/9 に**書類で解除できた**
- しかしその先に `NOT_ELIGIBLE` が残っており、新品FBAで作成した出品情報が自動削除された
- **FBMに変えても、コンディションを変えても、重複ASINを作っても解決しない**（重複ASIN作成はアカウント健全性に触るので不可）
- 結果：仕入れた12点（19,756円）は Amazon では1点も売れない

## ルールとして

- **「ブランドの出品許可が取れた」は「出品できる」ではない。** ゲートは2層あり、通ったのは `APPROVAL_REQUIRED` の層だけのことがある
- **CLAUDE.md §3.5 #2「出品ボタンの状態」は、まさにこの2層を見分けるための項目**。「この商品を出品する」が青＝`APPROVAL_REQUIRED` 以下、「出品を申請」がグレー＝`NOT_ELIGIBLE`
- **FBA/FBM の切り替えを「打つ手」として数えない。** モデル上、分岐点が存在しない

関連: [[knowledge_amazon_listing_restrictions_ungating]]、[[knowledge_amazon_lifecycle_checklist]]
