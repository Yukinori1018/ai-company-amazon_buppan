---
ticket_id: T-20260612-001
title: セミナー画面収録(6GB)のフレーム抽出・取りこぼしスライド確認
status: doing
assignee: researcher
priority: medium
created_at: 2026-06-12
updated_at: 2026-06-12
requires_approval: false
labels: [knowledge, maker-shiire, intake]
parent_ticket: T-20260610-001
---

## 要件

メーカー仕入れセミナー（2026-06-10）の画面収録（109分・映像のみ・音声トラックなし）から ffmpeg のシーン検出でフレームを抽出し、既存スクショ28枚でナレッジ化済みの内容と突合。**撮り損ねたスライド／Keepa操作デモ等の追加情報**があれば seminar-20260610-realtime-notes.md に追補する。

- 素材: `~/Documents/AI Company Outputs/Amazon物販事業/reference/maker-shiire-seminar-20260610/画面収録 2026-06-10 11.11.48.mov`
- 音声起こしは不可（音声トラック自体が存在しないことを ffprobe で確認済み）

## タスク分解

- [ ] ffmpeg シーン検出でフレーム抽出（agent_output 配下・リポ管理外）
- [ ] 抽出フレームをサトルが読み込み、既存28枚との差分（新規スライド・デモ画面）を特定
- [ ] 新情報があれば docs/reference/maker-shiire/seminar-20260610-realtime-notes.md に追補
- [ ] 結果を社長に報告（新情報なしならその旨）

## ログ

- 2026-06-12: 起票（社長指示=A案）。即着手。
