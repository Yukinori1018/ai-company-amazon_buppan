---
ticket_id: T-20260603-004
title: Satoy Select ロゴマーク制作（複数案）
status: done
assignee: content_creator
priority: medium
created_at: 2026-06-03
updated_at: 2026-06-03
completed_at: 2026-06-03
requires_approval: false
labels: [branding, design, logo]
---

## 背景

Amazon店舗名「Satoy Select」が確定（2026-06-01）。ブランド資産として
ロゴマークを用意する。社長が選べるよう複数案を提示する。

- コンセプト: 国内未進出のニッチ良品を発掘・"選び抜いて"届けるセレクトショップ
- 「Select」= キュレーション/目利き が核
- 用途: Amazon出品者プロフィール、納品書、将来のサンクスカード/ブランディング

## 担当

- コンテンツ制作（ヒデアキ）が制作。秘書カズヨが統合・納品。

## 成果物（予定）

- ロゴSVG 複数案（拡大しても劣化しないベクター）
- 一覧プレビューHTML（社長が見比べる用）
- 各案の意図メモ

## ログ

- 2026-06-03 起票・着手（カズヨ→ヒデアキ）
- 2026-06-03 ロゴ4案（A目利き印/B宝石/Cモノグラム/D値札）+ 比較HTML 制作完了。deliverables直納・社長閲覧用フォルダへコピー。→ waiting（社長の方向性選択待ち）
- 2026-06-03 社長が【A案：目利きの印】で確定。final/ に確定版を制作 → done。
  - フルロゴSVG（透過/白）+ アイコンSVG（透過線画/紺円塗り）
  - PNG書き出し9点（フル1280/640×透過/白、アイコン512/256/128透過・navy512/256）
  - 使い分けガイド README_logo-usage.md 添付。Amazonプロフィール用は icon_navy_512.png 推奨
  - PNG化は headless Chrome が不安定（プロセス未終了・tmp枯渇）→ 透過縮小は sips、紺アイコンは qlmanage で確実生成
