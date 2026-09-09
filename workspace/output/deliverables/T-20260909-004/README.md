# T-20260909-004 成果物インデックス

チケットの `## 成果物` 節を **Notion カード本文にも反映する**運用への是正。

社長の指摘（2026-09-09）:
> 「タスクのカードは作られていたけど、肝心のそのタスクが実行されていないよ。実際、このカードにも"成果物"の欄がないでしょ」

それまでの作業はローカルの `.md` 138枚に節を入れただけで、社長が実際に見る Notion カードには何も入っていませんでした。

## このフォルダの中身

| ファイル | 内容 |
|---|---|
| `README.md` | このファイル |
| `01_notion反映の手順.md` | Notion カード本文へ成果物欄を入れる手順（再実行手順つき） |

## 実装本体（リポジトリ内）

| 場所 | 役割 |
|---|---|
| [`scripts/notion/build_deliverable_blocks.py`](../../../../scripts/notion/build_deliverable_blocks.py) | チケットの `## 成果物` 節 → Notion 本文用 Markdown への変換器。リンク検証つき |
| [`agents/general_affairs/skills/notion-ticket-sync.md`](../../../../agents/general_affairs/skills/notion-ticket-sync.md) | 恒久ルール（§9 成果物節の Notion 反映） |

## リンクの作り方

Notion からは相対パスも `file://` も開けません。T-20260909-003 で作った成果物配信サーバの URL を使います。

```
http://localhost:17325/<ticket_id>/<ファイル名>
```

- ルートは `workspace/output/deliverables/`
- 日本語ファイル名はパスセグメントごとに percent-encode
- ポートは環境変数 `CATALOG_PORT`（既定 17325）。`scripts/catalog/build_catalog.py` と揃えること
- サーバ起動：`python3 scripts/catalog/serve_deliverables.py`

## 実績（2026-09-09）

- 処理カード **138枚**（＋ TicketID 重複カード1枚 = 計139回の書き込み）
- 生成リンク **614本**、全件 HTTP 200 を実測確認
- 既存本文は追記のみ（削除・上書きなし）
