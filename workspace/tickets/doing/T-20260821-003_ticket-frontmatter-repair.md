---
ticket_id: T-20260821-003
title: チケット frontmatter の修復（assignee 欠落13枚）＋Notion/社長タスク同期
status: doing
assignee: general_affairs
priority: high
created_at: 2026-08-21
updated_at: 2026-08-21
requires_approval: false
labels: [tickets, notion]
parent_ticket: T-20260821-001
next_check_at: 2026-08-22
---

## 要件

2026-08-11以降のチケット13枚で `assignee:` が欠落し `owner:` / `id:` に化けている。
テンプレ（`ticket_id:` / `assignee:`）に揃え、フックとNotion同期が正しく効く状態に戻す。

## タスク分解

- [x] 13枚の frontmatter を修復（`id:`→`ticket_id:`、`owner:`→`assignee:`）
- [x] 内容から見て本来の担当を推定して assignee を設定（判断に迷うものは secretary のまま＋メモ）
- [x] テンプレ `_template.md` との整合確認＋キー名変更禁止の注意書き追加
- [x] Notion カンバンへ同期
- [x] workspace/owner-tasks.md を最新化
- [x] メモリ記録（`agents/general_affairs/memory/ticket-frontmatter-contract.md`）

## 現在地

**マリエの作業は完了。カズヨのレビュー待ち（done 判定は秘書の責務のため doing に留置）。**

## 成果物

成果物は「納品ファイル」ではなくリポジトリ本体の修復。差分は git で追跡可能。

| 対象 | 内容 |
|---|---|
| `workspace/tickets/*/*.md`（13枚） | frontmatter 修復（`ticket_id` / `assignee` / `updated_at`）＋各チケットのログに修復記録 |
| `workspace/tickets/_template.md` | `next_check_at` / `related_tickets` を追加。frontmatter 直下に**キー名変更禁止の警告ブロック**を追加 |
| `docs/notion-board-schema.md` | Assignee の選択肢表に `it_engineer` / `owner` を追加（スキル側と乖離していた） |
| Notion「Amazon物販事業 Tickets」 | 未登録9枚のカード新規作成＋既存6枚の Assignee/UpdatedAt 更新。**対象17枚すべて整合確認済み** |
| `workspace/owner-tasks.md` | 最終更新の要約に「委譲ルールの是正に着手」を追記＋自動進行セクションに T-20260821 系の1項目を追加 |
| `agents/general_affairs/memory/ticket-frontmatter-contract.md` | 新規。frontmatter＝機械契約であること、ドリフト検知コマンド |
| `agents/general_affairs/memory/notion-sync.md` | リコンサイル前のドリフト検査手順を追記 |

## 修復した13枚の assignee 一覧

| ticket_id | 修復後 assignee | 根拠 |
|---|---|---|
| T-20260811-001 | content_creator | 既存 `owner:` を踏襲（マニュアル作成＝制作） |
| T-20260814-001 | **owner** | 既存 `owner: owner` を維持。残作業は社長本人の申込・決済のみ |
| T-20260816-001 | researcher | 既存踏襲（料金の事実収集） |
| T-20260816-002 | content_creator | 既存踏襲（手順マニュアル） |
| T-20260816-003 | planner | 既存踏襲（**判断メモあり**：実装フェーズでは it_engineer 再割当を検討） |
| T-20260817-001 | researcher | 既存踏襲 |
| T-20260817-002 | planner | 既存踏襲（方針立案） |
| T-20260817-003 | researcher | 既存踏襲 |
| T-20260817-004 | researcher | 既存踏襲 |
| T-20260817-005 | researcher | 既存踏襲 |
| T-20260817-006 | **secretary（据え置き）** | 事実確認=researcher／資料化=content_creator の混成で断定不可 |
| T-20260820-001 | legal | 既存踏襲 |
| T-20260820-002 | **secretary（据え置き）** | 税務=accounting／法令=legal／手順書=content_creator に跨り断定不可 |

## 完了報告（カズヨ宛）

**1. 直したもの**
13枚すべて `ticket_id:` / `assignee:` へ統一しました。ドリフトはゼロ件です（`grep -L "^assignee:"` / `grep -l "^id:"` ともに空）。
ついでに欠落していた `updated_at:` も補完しています（Notion の UpdatedAt 列が写せないため）。本文・既存フィールドには一切手を触れていません。

**2. Notion 同期＝可能でした（全17枚 整合済み）**
ただし想定外が1つ。13枚のうち **8枚はすでに正しい Assignee でカード化されており、残り5枚はそもそも Notion に一度もカードが作られていませんでした**（T-20260811-001 / T-20260814-001 / T-20260816-001・002・003）。
frontmatter のドリフトとは別に、**起票時の同期そのものが漏れていた**ということです。この5枚と新規4枚（T-20260821-001〜004）、計9枚を新規作成しました。
`Labels` は Notion 側の選択肢が「まとめ」のみで、`organization` 等の未定義ラベルを投げると失敗するため**今回は同期していません**。選択肢を足すか諦めるかはご判断ください。
`priority` を持たない5枚は Notion の Priority 列を**空のまま**にしました。私が推測で埋めると「勝手に決めた優先度」が既成事実になるためです。起票者側で入れてください。

**3. 迷って secretary に留めたもの＝2枚**
- **T-20260817-006**（信用構築の事前準備リスト）— チケット本文の「担当」節自体が「事実確認=リサーチャー領域／資料化=コンテンツ制作領域、ただし今回はカズヨが直接実施」と書かれており、混成のうえ現在HP制作が進行中。単一担当を断定できませんでした。
- **T-20260820-002**（開業届の提出支援）— 税務手続・法令解釈・手順書化に跨ります。前例の T-20260820-001（古物商）は legal でしたが、開業届/青色申告は accounting 寄りとも読め、断定を避けました。

この2枚は**まさに「抱え込みが起きた現場」そのもの**です（本来サブエージェントに振るべき作業をカズヨが直接実施した、と本文に明記されている）。親 T-20260821-001 の観点で、再ルーティングの判断をお願いします。

**4. ついでに見つけた別のドリフト（今回は直していません）**
- `related_tickets`（39枚）と `related`（12枚）の表記ゆれ。どちらも機械が読んでいないため実害ゼロ。一括置換は履歴を汚すので保留し、テンプレに正を明記するに留めました。
- `docs/notion-board-schema.md` の Assignee 表に `it_engineer` / `owner` が無く、スキル側 `notion-ticket-sync.md` とズレていました（**文書間のドリフト**）。これは実害があるため追記済みです。

**5. 🚨 検証中に見つけた重大バグ（担当外のため手を出していません）**

修復後に「本当にリマインダーのID欄が埋まるか」を確かめるため `.claude/hooks/session-start.sh` を実走したところ、
**リマインダーが1件も出ませんでした。ID欄が空だったのではなく、リマインダー機能そのものが最初から動いていません。**

原因（`bash -x` で特定）:

```
TICKETS_DIRS="$REPO/workspace/tickets/doing $REPO/workspace/tickets/waiting"
for TICKETS_DIR in $TICKETS_DIRS   # ← クォートなし＝空白で分割される
```

このリポジトリのパスは `/Users/yukinori/Claude Code/...` と**フォルダ名に空白を含みます**。
そのため `$TICKETS_DIRS` が `/Users/yukinori/Claude` と `Code/ai-company-.../doing` に割れ、
`[ -d ... ]` が両方 false → `continue` → **走査対象ゼロ**。`next_check_at` が何件期限切れでも無言で終わります。
現在 doing/waiting に **期限切れ33件**がありますが、1件も通知されていません。

これは私の担当（庶務）ではなく**IT エンジニア（タカシ）領域**なので、SUBAGENT_PROTOCOL §4 に従い自分では直しませんでした。
T-20260821-002（フック整備／assignee=it_engineer）が同じ `.claude/hooks/` を触っているので、**そちらに合流させるのが最短**だと思います。
修正自体は配列化（`TICKETS_DIRS=("$REPO/.../doing" "$REPO/.../waiting")` ＋ `for d in "${TICKETS_DIRS[@]}"`）で済みます。

> **この一件が、今回のドリフトが10日間気づかれなかった理由**でもあります。
> 「担当欄が消えた」ことと「リマインダーが死んでいた」ことが重なり、検知の網が二重に破れていました。

**6. ご提案**
キー名の警告文を書きましたが、正直これだけでは再発を止められないと思います（`owner` と `assignee` は日本語にするとどちらも「担当」で、書いた本人には違いが見えないためです）。
T-20260821-002 で IT エンジニアが委譲チェックフックを作る際、**frontmatter キーの検証を同じフックに相乗りさせる**のが確実です。ご検討ください。

完了しました。確認をお願いします。

## ログ

- 2026-08-21 doing 起票
- 2026-08-21 マリエ着手。13枚の frontmatter を修復（`id:`→`ticket_id:` / `owner:`→`assignee:` / `updated_at` 補完）。ドリフト残ゼロを確認。
- 2026-08-21 `_template.md` に `next_check_at` / `related_tickets` を追加、キー名変更禁止の警告を追記。`docs/notion-board-schema.md` の Assignee 表に `it_engineer` / `owner` を追加。
- 2026-08-21 Notion 同期完了。未登録9枚を新規作成＋既存6枚を更新し、対象17枚すべて整合を確認。
- 2026-08-21 `workspace/owner-tasks.md` 更新、メモリ2件（新規1・追記1）を記録。マリエ作業完了・カズヨのレビュー待ち。
