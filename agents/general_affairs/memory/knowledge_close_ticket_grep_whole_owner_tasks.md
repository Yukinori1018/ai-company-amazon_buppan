# チケットを閉じるときは owner-tasks.md 全体を ID で grep する（2026-09-12 / T-20260726-003）

## 何が起きたか
更新⑭（T-20260909-001 → doing、T-20260726-003 → done）で、依頼の指示は「更新⑬の `[ ]` を `[x]` に」だけだった。
しかし owner-tasks.md の **1398 行目（7/27 当時の古い節）にも T-20260726-003 の `[ ]` が残っていた**。依頼文だけを見ていたら見落としていた。
また更新⑬を `<details>` に畳む時、⑬ 本文の `[ ]` もそのまま残っていた（畳む前チェックで拾えた）。

## 手順（再利用可）
1. 冒頭の最優先ブロックを新しい更新番号で書き換え、旧ブロックを `<details>` で畳む
2. **畳む範囲の `[ ]` を確認**：`sed -n '/更新⑬の記載/,/<\/details>/p' owner-tasks.md | grep '\[ \]'`
3. **動いたチケット ID でファイル全体を grep**：`grep -n '\[ \]' owner-tasks.md | grep -E '<ID1>|<ID2>'`。done になった ID の `[ ]` は全部 `[x]` にする
4. 最終更新行（12 行目）の先頭に要約を追記（前の要約は「／前:」で残す）
5. waiting 突合：`workspace/tickets/waiting/T-*.md` の各 ID が owner-tasks.md に1回以上出るか＋ Notion の waiting 列（rows モード・Status=waiting フィルタ）と件数比較
6. Notion は update_properties → insert_content（position start）→ **fetch で読み返し**
7. commit は触ったファイルだけ明示的に add

## Notion ドリフトの見分け方
- 2026-09-12 時点で Notion waiting 27 件、ローカル waiting 26 件。差分は **T-20260806-002**（社長プロファイル整理）。
- ファイルはローカルのどのフォルダにも無い。`git branch -a --contains fac128d` で見ると、未マージのリモートブランチ `claude/employment-support-outsourcing-20p283` にだけある。
- **ブランチ分岐が原因のドリフト**。原因が同期漏れではないので、カード削除も勝手なファイル復元もしない（非破壊原則）。秘書に報告し、ブランチをマージするか取り込むかを判断してもらう。

## PUBLIC リポでの書き方
住所・電話・カード番号は書かない。「正しい国内住所」「古い海外住所」「誤字の氏名」までの抽象度に留める。
