# Claude Code 自律リサーチ資産（リポジトリ内の控え）

Claude Code の自律リサーチ用スキル `research` と、それが指揮するサブエージェント3体の**控え**です。

## これは控えです。正ではありません

| | 場所 | Git |
|---|---|---|
| **正（実体）** | ホームディレクトリ配下の `~/.claude/`（下表参照） | 追跡外 |
| **控え（このフォルダ）** | `docs/reference/claude-research-skill/` | **追跡する** |

Claude Code が実際に読み込むのは `~/.claude/` 側の実体だけです。**このフォルダのファイルを編集しても動作は変わりません。**
ここは「`~/.claude/` を初期化・移行・PC 買い替えした際に復元できるようにしておく」ためだけの控えです。

## 由来

| | |
|---|---|
| 資産の導入 | [T-20260902-002](../../../workspace/tickets/done/T-20260902-002_autonomous-research-agents-install.md)（社長が `_inbox_社長共有/files3/` へ投函 → `~/.claude/` へ設置） |
| この控えの作成 | T-20260902-003（上記の後続。社長が A 案「リポジトリ内に控えを置く」を採用） |

**なぜ控えが要るのか:** 導入先の `~/.claude/` はリポジトリ外で Git 追跡されず、inbox アーカイブ側
（`_inbox_社長共有/_archive/2026-09/T-20260902-002_自律リサーチagent-skill/`）も `.gitignore` 対象です。
つまり T-20260902-002 の完了時点で、この5ファイルは**どこにもバックアップが無い資産**でした。

## ファイルと復元先

`~` はこの Mac のホームディレクトリです。コピー先の絶対パスは `~` を展開したものになります。

| このフォルダ内のパス | 復元先（絶対パス） | 種別 |
|---|---|---|
| `skills/research/SKILL.md` | `~/.claude/skills/research/SKILL.md` | スキル本体 |
| `skills/research/references/external-sources.md` | `~/.claude/skills/research/references/external-sources.md` | スキル参照資料 |
| `agents/research-collector.md` | `~/.claude/agents/research-collector.md` | サブエージェント（収集） |
| `agents/research-verifier.md` | `~/.claude/agents/research-verifier.md` | サブエージェント（検証） |
| `agents/research-integrator.md` | `~/.claude/agents/research-integrator.md` | サブエージェント（統合） |

このフォルダのディレクトリ構造は `~/.claude/` 配下の構造をそのまま再現しています。
`external-sources.md` が `references/` 配下にあるのは、`SKILL.md` 本文 §B が相対パスで
`references/external-sources.md` を参照しているためです。**この位置を動かすと参照が切れます。**

### 復元手順

```bash
mkdir -p ~/.claude/skills/research/references ~/.claude/agents
cp docs/reference/claude-research-skill/skills/research/SKILL.md                       ~/.claude/skills/research/SKILL.md
cp docs/reference/claude-research-skill/skills/research/references/external-sources.md  ~/.claude/skills/research/references/external-sources.md
cp docs/reference/claude-research-skill/agents/research-collector.md                    ~/.claude/agents/research-collector.md
cp docs/reference/claude-research-skill/agents/research-verifier.md                     ~/.claude/agents/research-verifier.md
cp docs/reference/claude-research-skill/agents/research-integrator.md                   ~/.claude/agents/research-integrator.md
```

復元後、`cksum` で控えと復元先が一致することを確認してください。

## ⚠️ `~/.claude/` を編集したら、この控えも更新すること

控えは**自動では追随しません**。実体を書き換えたのに控えを放置すると、
控えが古いまま「バックアップがある」と思い込む状態になり、これは**バックアップが無いより危険**です。

実際、2026-09-02 の時点で inbox アーカイブ側の `SKILL.md` は既に実体と食い違っていました
（同日中に2回編集されたため。アーカイブ側 6,612 バイト / 実体 7,269 バイト）。
この控えは**実体側の現行版**から取っています。

`~/.claude/skills/research/` または `~/.claude/agents/research-*.md` を編集したら、
同じ turn 内でこのフォルダへコピーし直し、`cksum` で照合して commit してください（庶務マリエの作業）。

## 作成時点の照合記録（2026-09-02）

`cksum`（CRC32 とバイト数）で実体と控えを照合。5件すべて一致。

| ファイル | cksum | bytes |
|---|---|---|
| `SKILL.md` | 950465037 | 7269 |
| `external-sources.md` | 1680549349 | 2497 |
| `research-collector.md` | 2342105512 | 2983 |
| `research-verifier.md` | 81074490 | 2158 |
| `research-integrator.md` | 2923363647 | 2388 |

5ファイルの中身は**一字も変更していません**。整形・要約・改善は加えていません。
