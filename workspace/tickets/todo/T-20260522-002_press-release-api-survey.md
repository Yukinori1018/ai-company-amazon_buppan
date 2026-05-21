---
ticket_id: T-20260522-002
title: プレスリリース・新商品情報 API 調査（Sato-Scope 拡張源）
status: todo
assignee: researcher
priority: medium
created_at: 2026-05-22
updated_at: 2026-05-22
requires_approval: false
labels: [research, sato-scope, supplier-expansion]
related_tickets: [T-20260521-005]
parent_ticket: T-20260521-005
---

## イシュー

> 朝野氏「Amazon ブラックフライデー刈り取り」と同じ発想で、新商品発売・セール開始タイミングを **公開情報経由で合法的に取得する手段**を整理する。

## 調査対象

1. PR TIMES API
2. @Press API
3. ValuePress
4. 共同通信 PR ワイヤー
5. 楽天スーパー DEAL RSS / 楽天市場新着 RSS
6. 価格.com ニュース RSS
7. ヤフー!ショッピング 特売情報フィード
8. メーカー公式 X（プレミアムバンダイ・各家電メーカー）の Twitter API v2 利用可否

## 各 API で確認したいこと

| 確認項目 | 期待する出力 |
|---|---|
| 料金 | 無料 / 月額 |
| データ粒度 | 商品単位 / カテゴリ単位 / ジャンル単位 |
| リアルタイム性 | リリース直後 / 数時間遅延 |
| カテゴリフィルター | 物販に関係するカテゴリだけ抽出可能か |
| 二次利用 ToS | 仕入れ判断ツール内表示 OK か |
| Sato-Scope への組み込み難度 | 高/中/低 |

## 打ち切り条件

- 上記 8 系統について、各 20〜30分でドキュメント確認まで
- 「物販で実用上使えそうなもの 3 つ以上」「使えなさそう」と判断できた時点で打ち切り

## バトン

調査完了後、タケシが「Sato-Scope v0.2 で組み込むべき API 3 選」を提案。社長判断で実装。

## 現在地

todo。サトル発注待ち。

## ログ

- 2026-05-22 起票（社長 A1 承認に基づく並行調査チケット）
