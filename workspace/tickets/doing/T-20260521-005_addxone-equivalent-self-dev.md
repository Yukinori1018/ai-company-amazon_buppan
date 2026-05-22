---
ticket_id: T-20260521-005
title: ADD×ONE PROJECT 同等の社長専用 物販リサーチツール 自社開発検討
status: doing
assignee: it_engineer
priority: high
created_at: 2026-05-21
updated_at: 2026-05-22
next_check_at: 2026-05-23
requires_approval: true
labels: [dev, research, mvp, tooling]
related_tickets: [T-20260520-006]
---

## 要件

社長依頼: ADD×ONE PROJECT（物販ONE グループ独自開発、150万円コース付属推定）と同等の **社長専用** Amazon 物販リサーチツールを自社で作れないかの検討。

> 「できれば、私専用で私しか使わないので、簡易的な同じような役割を持ったアプリないしWebアプリないしWebサイトを作ることはできないでしょうか」 — 社長 2026-05-21

## 機能イメージ（ADD×ONE PROJECT 観察より）

- カテゴリ別検索プリセット（ADD×ONE では「宝の地図1〜15」）
- Keepa API 連携で Amazon 側データ取得
- 価格比較サイト（Yahoo!ショッピング 等）から仕入候補取得
- 利益計算 + 判定フラグ（原石／あやしい／はずれ）
- 結果テーブル: ASIN / タイトル / 売値 / 仕入値 / 利益 / 利益率 / 月販 / Drop30 / 仕入元

## 想定構成案（暫定）

| 構成要素 | 案 |
|---|---|
| バックエンド | Python (FastAPI) + SQLite |
| フロント | 最小 Web UI（社長専用・ベーシック認証） |
| Amazon データ | **Keepa 公式 API**（€49/月） |
| Yahoo!ショッピング | **公式 Web サービス API**（無料枠あり、ToS 安全） |
| 利益判定 | 売値 × Keepa 推定 × 仕入値 × FBA手数料 → 原石/あやしい/はずれ |
| ホスティング | Vercel / Railway 等（月数百円） |
| 月額ランニング | 約 9,000〜10,000円（Keepa 主） |

ADD×ONE はスクレイピング方式と推定だが、本案は **Yahoo!公式 API を使うため ToS 違反リスクなし** が法務観点の優位。

## §4.1 該当事項（社長承認必須）

1. **IT エージェント新規雇用**（agents/it_engineer/agent.md 整備、CLAUDE.md §2 追記）= 仕組みの追加
2. **開発時間コスト発生**（AI 側）
3. Keepa API 課金（€49/月＝約9,000円）= 月額サブスク追加

## タスク分解（社長承認 A 取得後の想定）

- [ ] A/B/C の社長判断（**A 推奨: IT エージェント「タカシ」雇用**）
- [ ] A の場合: `agents/it_engineer/agent.md` 起票・CLAUDE.md §2 追記
- [ ] 経理ハジメ並列発注: 開発・運用コスト試算と ROI 評価
- [ ] 法務ハルオ並列発注: Keepa API + Yahoo!公式 API + Amazon ToS の整合確認
- [ ] IT タカシ（or 代替）: MVP 設計 → 実装 → 社長確認
- [ ] コンテンツ制作ヒデアキ: 社長向け使い方マニュアル

## 社長判断ポイント（A/B/C）

- **A（秘書推奨）**: IT エージェント「タカシ」新規雇用。MVP 開発を担当
- **B**: 既存エージェント（経理＋庶務）で代替対応（精度・速度落ちる）
- **C**: 外注検討（コスト・契約発生で §4.1 案件に）

## 現在地

**Phase 0 完了**（2026-05-22）。サトル・タケシ・タカシ3者合作で以下を納品、社長レビュー待ち。

- `workspace/output/deliverables/T-20260521-005/01_tool-overview.md` — ツール概要・MVP仕様
- `workspace/output/deliverables/T-20260521-005/02_mockup.html` — HTML モック
- `workspace/output/deliverables/T-20260521-005/03_research-and-strategy.md` — リサーチ＆戦略ログ
- `workspace/output/deliverables/T-20260521-005/README.md`

A/B/C 判断後に Phase 1（API 接続検証）着手。Phase 1 時点で Keepa API €49/月課金の §4.1 承認を改めて取得。

## ログ

- 2026-05-21 起票。社長依頼受領 → A/B/C 提案
- 2026-05-21 社長 A 承認（IT エージェント「タカシ」新規雇用で進行）
- 2026-05-22 タカシ正式登用（`agents/it_engineer/agent.md` 作成、CLAUDE.md §2/§5 追記）
- 2026-05-22 Phase 0 納品。3者合作で概要・モック・戦略ログを deliverables 配置
- 2026-05-22 社長レビューで方向性指摘（「商品決まっている前提か？」） → 完全方向転換。Product Lookup 型 → **Discovery 型**へ
- 2026-05-22 D1〜D9 議論を経て差別化軸を質的方向（D3/D4/D5/D6/D8）に確定。Amazon は販売参照のみで仕入れ元から除外
- 2026-05-22 **モック v0.2 を Discovery 型に書き換え**。8件サンプル・ソート/フィルター/ポイント込み価格トグル/★お気に入りが実動
- 2026-05-22 並行調査 3 チケット起票（T-20260522-001 B2B卸API/002 PR-API/003 アフィリエイトASP-ToS）。A1 承認に基づき走らせるが実装は社長判断待ち
- 2026-05-22 社長 A 承認 → **Phase 1 着手**。タカシがコードベース構築：
  - `code/app/calc/profit.py`（FBA/自己発送/MSS 真の利益計算）+ ユニットテスト全通過
  - `code/app/calc/score.py`（おすすめスコア + 🟢🟡🔴 判定）
  - `code/app/compliance/brand_warnings.py`（Sony/Apple/Nike 等の警告マスタ）
  - `code/app/adapters/{keepa,rakuten,yahoo}.py`（モック実装、Phase 2 で実 API 接続）
  - `code/app/main.py`（FastAPI /search /health エンドポイント）
  - 動作確認: `/search` が 7 件抽出、スコア降順、Sony 警告も発火
- 2026-05-22 Phase 2 着手前の並行発注 2 チケット起票:
  - T-20260522-004 Sato-Scope ROI 試算（ハジメ）
  - T-20260522-005 公式 API ToS 最終確認（ハルオ）
- 2026-05-22 Phase 2 着手の §4.1 承認待ち（Keepa €49/月 + 楽天/Yahoo! ApplicationID 登録）
- 2026-05-22 **社長レビューでモック OK、Phase 2 即 GO 承認取得**。Keepa Power-User Plan €49/月 課金 §4.1 承認確定。次は社長手作業で Keepa 申込＋楽天 ApplicationID＋Yahoo! ClientID 取得（カズヨが手順書を提示）
