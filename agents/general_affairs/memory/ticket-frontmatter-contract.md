# メモリ：チケット frontmatter は「機械が読む契約」（マリエ）

## 事件（2026-08-11〜2026-08-21 / T-20260821-003）

2026-08-11 以降に起票された13枚が、テンプレの `ticket_id:` / `assignee:` ではなく
**`id:` / `owner:`** という別名で書かれていた。人間の目には同義でも、機械には別物だった。

被害は3段:

1. `.claude/hooks/session-start.sh` は frontmatter を **awk で `^ticket_id:` 直読み**する。
   `id:` では一致せず、日次リマインダーの ID 欄が**空文字**で出続けた。
2. Notion 同期は `assignee` → Assignee 列に 1:1 マップ（`docs/notion-board-schema.md`）。
   `owner:` は写像対象外なので、**担当列が空のまま**カードが並んだ。
3. いちばん重い被害＝**担当を書く欄が消えれば、振り分けという行為自体が消える。**
   秘書の抱え込み再発（親 T-20260821-001）の構成要因のひとつになった。

> 教訓：**frontmatter のキー名はドキュメントではなく契約（API）。**
> 値の空欄は無害だが、キーのリネームは静かに機能を壊す。しかも壊れても誰もエラーを出さない。

## ドリフトの検知方法（3コマンド・毎回これで足りる）

```bash
cd <repo>
grep -L "^assignee:"  workspace/tickets/*/*.md   # assignee 欠落
grep -L "^ticket_id:" workspace/tickets/*/*.md   # ticket_id 欠落（フックが読めない）
grep -l  "^id:"       workspace/tickets/*/*.md   # 旧名 id: の残存
```

キーの使用頻度を俯瞰してゆれを炙り出す（少数派＝たいてい表記ゆれ）:

```bash
for f in workspace/tickets/*/*.md; do
  awk '/^---$/{n++; if(n==2) exit} n==1 && /^[a-z_]+:/{sub(/:.*/,""); print}' "$f"
done | sort | uniq -c | sort -rn
```

**`/sync-notion` の冒頭でこの検知を必ず回すこと。** ドリフトを抱えたまま同期すると、
Notion 側は「担当なしのカードが正しい」という誤った鏡になる。

## 未解決として残した表記ゆれ

- **`related_tickets`（39枚）vs `related`（12枚）** — どちらも機械が読んでいないため実害ゼロ。
  実害が出る前に統一したいが、勝手な一括置換は履歴を汚すので保留。テンプレ側には
  `related_tickets` を正として明記済み。
- **`priority` / `labels` 欠落が11枚** — Notion の Priority 列が空になる。値を推測して埋めると
  「マリエが勝手に決めた優先度」が既成事実化するので、**あえて埋めなかった**。
  起票者（秘書）が入れるべき欄。

## 再発防止で入れたもの（2026-08-21）

- `workspace/tickets/_template.md` の frontmatter 直下に
  **「キー名は変更するな＝フック/Notion同期が参照する」警告ブロック**を追加。
  どのキーを誰が読むかを名指しし、`assignee` の固定語彙10種も併記した。
- `docs/notion-board-schema.md` の Assignee 表に `it_engineer` / `owner` を追加
  （スキル側 `notion-ticket-sync.md` には既にあり、スキーマ文書だけが古かった＝**文書間のドリフト**）。

## ときめき判定の記録

`owner:` は「所有者」で `assignee:` は「割当先」。日本語にすると同じ「担当」で、
**書いた本人には違いが見えない**。だから注意書きだけでは止まらない。
本当に止めたいなら、機械が読むキーは機械にチェックさせる（フック化）のが筋。
→ T-20260821-002（IT エンジニア）で委譲チェックフックを作る際に、
**frontmatter キーの検証も同じフックに相乗りさせられないか**、カズヨ経由で提案したい。

## 併せて発見：リマインダーフックが最初から動いていなかった（2026-08-21）

修復後の検証で `.claude/hooks/session-start.sh` を実走したところ、**リマインダーが1件も出なかった**。
ID欄が空だったのではなく、機能そのものが死んでいた。

原因は frontmatter ではなく **シェルのクォート漏れ**:

```bash
TICKETS_DIRS="$REPO/workspace/tickets/doing $REPO/workspace/tickets/waiting"
for TICKETS_DIR in $TICKETS_DIRS   # クォートなし → 空白で単語分割
```

このリポジトリのパスは `/Users/yukinori/Claude Code/...` と**フォルダ名に空白を含む**。
`$TICKETS_DIRS` が `/Users/yukinori/Claude` と `Code/...` に割れ、`[ -d ]` が両方 false → 全 continue → 走査ゼロ。
期限切れ33件が無言で握り潰されていた。

**教訓：フックは「壊れても何も言わない」。** 出力が空なのが「該当なし」なのか「壊れている」のかを
区別できない設計になっている。**フックを直したら必ず実走して出力を目で見る**こと。
検証コマンド:

```bash
CLAUDE_PROJECT_DIR="$PWD" bash -x .claude/hooks/session-start.sh 2>&1 | head -30
```

修正は it_engineer 領域のため手を出さず、T-20260821-002 への合流をカズヨに提案した
（SUBAGENT_PROTOCOL §4「担当外と判明 → 秘書に差し戻し・自分で再ルーティングしない」）。

> **今回のドリフトが10日間気づかれなかった真因は、この二重の破れ**
> ＝「担当を書く欄が消えた」＋「期限切れを知らせる仕組みが死んでいた」。
> 片方だけ直しても検知は戻らない。
