# Notion の未登録ラベルは、カード作成の前に「選択肢」を足す

初出: 2026-09-06 / T-20260906-001（PHS-101CM 供給空白調査カードの新規作成）

## 何が起きたか

チケット frontmatter の `labels: [research, keepa, sourcing-risk]` をそのまま
`notion-create-pages` に渡したら **400 validation_error** で落ちた。

> Invalid multi_select value for property "Labels": "sourcing-risk".
> If a new multi_select option is needed, the data source must be updated to add it.

`research` と `keepa` は既存だが、**`sourcing-risk` はこの日が初出のラベル**だった。
スキル `notion-ticket-sync.md` §3 に「未定義ラベルは事前に選択肢追加が必要」と一行だけ書いてあるが、
**追加のしかたは書かれていなかった**ので、ここに手順を残す。

## 手順（2手）

```
# ① 選択肢を追加（notion-update-data-source）
data_source_id: 366b0a40-44fa-81ec-8342-000b6d0a25e0
statements: ALTER COLUMN "Labels" SET MULTI_SELECT('既存1', '既存2', ..., '新規':orange)

# ② そのあとで notion-create-pages / notion-update-page
```

## ⚠️ 最大の落とし穴 — `ALTER COLUMN ... SET` は「全置換」

`SET MULTI_SELECT(...)` は差分追加ではなく **列の選択肢を丸ごと差し替える**。
新規ラベル1個だけを書くと、**既存の全選択肢が消え、既存カードのラベルが飛ぶ**（破壊的）。

**必ず既存の全選択肢を列挙し、末尾に新規を足した完全なリストを渡すこと。**
既存の一覧は、わざわざ fetch しなくても**エラーメッセージ本文がそのまま全列挙してくれる**ので、
1回失敗させてからそれをコピーするのが最短かつ最も安全（2026-09-06 はこの方法で33件を保持し34件目を追加した）。
書き込み後は返ってきた `<data-source-state>` で**件数が「元＋1」になっているか**を必ず数える。

## 前段でやっておくこと

作成前に `notion-query-data-sources`（SQL モード）で `TicketID` を引き、
**本当にカードが無いこと**を確認してから作る。二重カードは非破壊原則のせいで自動では消せない。

```sql
SELECT "TicketID","Name","Status" FROM "collection://366b0a40-44fa-81ec-8342-000b6d0a25e0"
WHERE "TicketID" = 'T-XXXXXXXX-XXX'
```

## ついでの学び

`sourcing-risk` のような**新カテゴリのラベルが出てきたこと自体が情報**だった。
「仕入れ先の供給が切れるリスク」を独立した観点として立てる必要が出てきた、という事業側の変化の印。
ラベルを足すときは、機械的に足すだけでなく **既存ラベルで代用できないかを一度考える**
（今回は `netsea` でも `keepa` でも表現できない別軸だったので新設が妥当）。

## 追記 2026-09-30 / T-20260930-001（ラベル `list` 追加）

- 手順どおり ① `notion-fetch collection://...` で現行の全選択肢と色を取得 → ② 全56件＋新規 `'list':gray` を `SET MULTI_SELECT` で投入 → ③ カード作成、で一発成功。
- **既存選択肢の option URL（ID）は SET 後も変わらなかった**＝名前と色を正確に全列挙すれば既存カードのラベルは飛ばない。レスポンスで末尾に新規1件だけ増えたことを件数で確認するのが検算。
- 新規起票1件の定型（所要4手）：Notion 既存カード検索（TicketID）→ 未登録ラベル確認・追加 → create-pages（本文に結果要約＋成果物節＋配信サーバ注記）→ fetch で読み返し。カタログは CSV 追記 → sync → 種別は既存値（計画／レポート等）に寄せ、新しい種別を増やさない。
