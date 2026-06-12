---
ticket_id: T-20260612-001
title: セミナー画面収録(6GB)のフレーム抽出・取りこぼしスライド確認
status: done
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

- [x] ffmpeg シーン検出でフレーム抽出（122枚）＋取り残し2区間を15秒間隔で追加抽出（258枚）
- [x] 抽出フレームをサトル9班が読み込み、既存28枚との差分を特定
- [x] docs/reference/maker-shiire/seminar-20260610-realtime-notes.md に §8 追補（費用表・AI問い合わせプロンプト・キーゾン計算式・在庫表列構成・WAM NETデモ手順等）＋メモリ更新
- [x] 結果を社長に報告

## ログ

- 2026-06-12: 起票（社長指示=A案）。即着手。
- 2026-06-12: 完了。最大の収穫=**コンサル費用表の復元**（Pro 198万→特別132万/Basic 132万→99万/Entry 66万、24回分割あり、返金は資料読込期間=最大1ヶ月のみ）。ほか返信率KPI30%・キーゾン計算式・在庫表実物列構成・WAM NET実機手順・取引依頼メールAIプロンプト全文を取得。音声トラックなしのためQ&A口頭回答は復元不可（確定）。フレーム原本は agent_output/T-20260612-001/ に保持（gitignore対象）。
