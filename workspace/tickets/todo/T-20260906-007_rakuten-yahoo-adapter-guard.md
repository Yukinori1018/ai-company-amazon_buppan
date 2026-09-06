---
ticket_id: T-20260906-007
title: 楽天/Yahooショッピングのアダプタに用途ガードを入れる（規約違反の疑い・現在は不稼働）
status: todo
assignee: it_engineer
priority: medium
created_at: 2026-09-06
updated_at: 2026-09-06
next_check_at: 2026-09-08
requires_approval: false
labels: [guardrail, legal, adapters]
related_tickets: [T-20260906-006, T-20260521-005, T-20260831-002]
---

## 背景（法務ハルオ・2026-09-06／T-20260906-006 の判定書 §V）

ハルオが依頼範囲外の自主確認で発見した。

- `workspace/output/deliverables/T-20260521-005/code/adapters/rakuten_shopping.py` / `yahoo_shopping.py` が実装済みで、ヘッダに「**仕入れ元起点＝電脳せどりの入口**」と明記されている
- **楽天ウェブサービス規約 Art.10(1)(4)**「楽天アフィリエイト以外の方法で Web Services を使って収益を得る行為」、(6)「競合サービスの提供」、(9)「不特定多数と共有できる場所への保存」に直撃する疑い
- `agents/it_engineer/memory/rakuten_new_api_referer_gatekeeper.md` に「**Yahoo は実APIで稼働中**」の記載あり
- Yahoo API はガイドライン未取得のため**判定保留**

Keepa・NETSEA に続く「**新機能は白だが既存運用が黒**」の3例目。

## 秘書の実測（カズヨ・2026-09-06 23:20 頃）

**結論：現に走ってはいない。緊急停止は不要。**

| 確認対象 | 結果 |
|---|---|
| `crontab -l` | 本リポの job なし（別プロジェクトの1件のみ） |
| `~/Library/LaunchAgents/` | `list-builder`（稼働・PID あり）／`github-sync`／`amazon-check-watchdog`／`night-shift` は **`.disabled`** |
| 稼働中の `list-builder` の中身 | `always_on.py`（T-20260831-002）を呼ぶだけ。`.claude/scripts/list-builder.sh` と `T-20260817-005/v14/` を grep して **rakuten / yahoo の参照はゼロ** |
| プロセス | `ps` に rakuten/yahoo を叩くものなし |
| 現在の状態 | `always_on.log` は「STOP ファイルがあるので待機します」＝**停止中** |

→ **アダプタは deliverables にコードとして存在するだけで、どのスケジュールからも呼ばれていない。**
①電脳せどりが 2026-08-10 社長指示で停止中であることとも整合する。

## やること

1. **`rakuten_shopping.py` / `yahoo_shopping.py` に用途ガードを入れる。** `adapters/netsea.py` の `assert_procurement_use()` と同型でよい。**呼ばれた瞬間に停止し、理由と根拠条番号を出す**こと
2. **Yahoo（LINEヤフー）API ガイドラインを取得してハルオへ回す。**判定保留を解消する
3. ガードのテストを1本足す

## やらないこと

- **コードの削除はしない**（§4.1 不可逆な削除）。ガードで塞ぐだけ
- launchd ジョブの停止・解除もしない（**そもそも呼ばれていない**ため不要）

## 優先度の判断

**medium。**現に違反行為が発生していないため緊急ではない。ただし①電脳せどりを再開した瞬間に踏む地雷なので、再開判断より前に塞いでおく。
今夜は T-20260906-003（母数引き直し）が Keepa トークンを使って自走中のため、**タカシへの発注は明日以降**とする。

## ログ

- 2026-09-06 起票。ハルオの §V 指摘を受け、秘書が稼働状況を実測。不稼働を確認したうえで todo に置いた。
