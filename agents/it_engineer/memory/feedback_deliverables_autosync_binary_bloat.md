# deliverables に大きな中間ファイルを置くと自動同期フックが即コミットする（2026-08-21 / T-20260817-005）

## 起きたこと

`workspace/output/deliverables/T-20260817-005/raw/` に Keepa の生レスポンスを
`*.json.gz`（1ファイル約6MB）で保存する設計にした。`.gitignore` を書く前に
**`chore(auto-sync)` フックが作業中のディレクトリごとコミット**し、23MB のバイナリが
履歴に入った。スキャンを完走すれば約40ファイル・**200MB超**がリポに入るところだった。

## 学び

1. **deliverables 配下は「置いた瞬間に Git に入る」と思って設計する。**
   自動同期フックは私の `git add` を待たない。数分で走る。
2. **中間バイナリを deliverables に置くなら、ファイルを1つでも生成する前に
   `.gitignore` を先に書く。** 「あとで .gitignore する」は間に合わない。
3. 既に入った履歴は `git rm --cached` で**追跡だけ止める**（ファイルはローカルに残る＝
   `--from-raw` の再集計に必要）。**履歴の書き換え（filter-branch / reset --hard / force push）は
   CLAUDE.md §4.1 該当なので自分では踏まない。** 秘書経由で社長に報告する。

## 設計の指針（次から）

| 種類 | 置き場 |
|---|---|
| 生API レスポンス・巨大な中間データ | `agent_output/<ticket_id>/`（gitignore済）か、deliverables 配下でも**先に .gitignore** |
| CSV・summary.json・スクリプト・README | deliverables 直下（Git 追跡してよい） |

ただし `agent_output/` は worktree 消滅で失われる（`feedback_deliverable_persistence`）。
**raw を残したいなら deliverables 配下 + .gitignore が正解**。今回の
`deliverables/T-20260817-005/.gitignore` に `raw/` を書く形が最終形。
