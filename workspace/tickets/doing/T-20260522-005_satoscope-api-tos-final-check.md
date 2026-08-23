---
ticket_id: T-20260522-005
title: Sato-Scope 公式 API 利用規約 最終確認（Keepa／楽天／Yahoo!）
status: doing
assignee: legal
priority: medium
created_at: 2026-05-22
updated_at: 2026-05-25
next_check_at: 2026-08-25
requires_approval: false
labels: [legal, sato-scope, tos-review]
related_tickets: [T-20260521-005]
parent_ticket: T-20260521-005
---

## イシュー

> Sato-Scope Phase 2 で実 API 接続する前に、Keepa／楽天市場／Yahoo!ショッピング の各公式 API の **2026 年最新版 ToS** を確認し、Sato-Scope の利用形態が規約範囲内であることを最終確認する。

## 確認対象 API

1. **Keepa API** Power-User Plan（€49/月）
   - 商用利用範囲
   - データ二次配信の可否（個人ツール内表示のみなので OK のはず）
   - レート制限と適切な再試行間隔
2. **楽天市場 商品検索 API**
   - ApplicationID の個人利用範囲
   - 商品データの内部利用範囲
   - 表示要件（楽天バナー/クレジット表記）
3. **Yahoo!ショッピング Web API**
   - ClientID 個人利用範囲
   - データの再利用範囲
   - 表示要件

## 確認項目（各 API 共通）

| 項目 | 期待アウトプット |
|---|---|
| 個人専用ツール内利用 | OK / NG / 条件付き OK |
| クレジット表記要件 | バナー必須 / リンク必須 / 不要 |
| データ保存（SQLite ローカル） | OK / 期間制限あり / NG |
| 利用規約違反時のペナルティ | アカウント停止 / API キー無効化 |

## 打ち切り条件

- 各 API について規約該当条文を抜粋し、Sato-Scope の利用形態が OK / 要修正 を判断できた時点

## バトン

ハルオ完了 → タカシが必要なら表示要件を Sato-Scope に組み込み（楽天バナー等）→ Phase 2 着手

## 現在地

todo。ハルオ発注待ち。

## ログ

- 2026-05-22 起票（Phase 2 §4.1 承認前の最終確認）
- 2026-05-25 社長「承認不要なものは全て進めて」＋Phase 2 継続方針 → todo → doing。ハルオ発注（§4.2）
- 2026-08-21 next_check_at=2026-08-25 を付与（マリエ／T-20260821-005）: ⚠️Keepa API を T-20260817-005 で実運用中なのに ToS 最終確認が未了。放置不可のため前倒し

---

## 現在地（2026-08-24 更新・ハルオ）

**Keepa API の ToS 確認は完了。** T-20260824-001 の並行発注（Keepa 公式 MCP サーバの法務レビュー）の中で、
Keepa の契約文書を一次情報で特定・全文取得し、本チケットの確認項目にすべて回答できる状態になった。

### Keepa API（Power-User Plan）— 確認結果

適用契約 = **Terms and Conditions for Keepa.com Price Data API - Data as a Service（Version of July 28, 2026）**
実URL: `https://keepa.com/cdn/termsAPI.txt`（確認日 2026-08-24）
※ サイト ToS（`#!disclaimer`）と Subscriptions T&C（Pro用）は**別文書**。混同すると結論が変わる。

| 本チケットの確認項目 | 判定 | 根拠条文 |
|---|---|---|
| 商用利用範囲 | **OK（むしろ事業者専用）** | §3(4) *"available solely for business purposes"* ／ §2(2) *"solely for the user's own business purposes"* |
| 個人専用ツール内での利用 | **OK** | 同上。ただし「個人（消費者）としての利用」は §3(4)/§5 により想定外。**事業として使うこと** |
| データ二次配信・再販 | **NG（事前書面同意が必要）** | §2(2)／§6.1(1) *"Resale of the data obtained from 'Keepa.com' is strictly prohibited"* |
| データ保存（SQLite/CSV ローカル） | **OK（明文で許諾）** | §11(2) 保存・印刷して自社業務目的で使う **non-exclusive and unlimited right of use** |
| 加工・翻訳・複製 | **⚠ 制限あり** | §11(1) modify / edit / **translate** / reproduce は express permission なしには不可。**公開は特に危険** |
| クレジット表記要件 | **条文上、表記義務の定めなし**（Keepa ロゴ・著作権表示の**除去・改変は禁止**＝§11(1)） | §11(1) |
| レート制限 | トークン制。§2(3) で Keepa が同時リクエスト数を制限できる | §2(3) |
| 違反時のペナルティ | **アクセス遮断（§13）＋契約解除（§12(3)）＋免責・補償義務（§14(1)）** | §12, §13, §14 |
| 規約改定 | **6週間前に text form で通知。異議を出さず使い続けると黙示承諾** | §19 |
| 準拠法・管轄 | ドイツ法／Keepa 所在地の専属管轄 | §20 |

**Sato-Scope（社内専用ツール）での利用形態は、上表の範囲内であれば OK。**
NG になるのは (a) データや機能の外販、(b) Keepa 由来データの公開・配布、(c) キーの第三者共有 の3つ。

### 残件（本チケットで未了）

- **楽天市場 商品検索 API** — 未確認
- **Yahoo!ショッピング Web API** — 未確認
- 上記2つは①電脳せどりホールドに連動して優先度が下がっている（T-20260821-005 の整理と同じ）。Keepa だけ先に決着した。

### ログ

- 2026-08-24 ハルオ：Keepa API の ToS 確認を完了（一次情報：API T&C 2026-07-28版）。詳細レビューは
  `workspace/output/deliverables/T-20260824-001/legal-review-keepa-mcp.md`、規約の要点は
  `agents/legal/memory/knowledge_keepa_tos.md` に恒久記録。楽天・Yahoo! は未着手のため本チケットは doing のまま。
