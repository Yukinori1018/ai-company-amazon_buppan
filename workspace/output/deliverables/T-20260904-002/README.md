# T-20260904-002 — ホームページ制作事業リポジトリの雛形生成 / 作業ログ

**担当:** IT エンジニア タカシ / **実施日:** 2026-09-04

> **成果物の本体はこのフォルダにはありません。** 生成先フォルダそのものが成果物です。
> ここに置いてあるのは「どこに何を作り、何を捨て、なぜそう判断したか」の作業ログです。

---

## 1. 生成先パス

```
/Users/yukinori/Claude Code/ai-company-homepage/
```

**本リポジトリ（`ai-company-amazon_buppan`）の外**に生成しました。理由は本リポが PUBLIC で
`.claude/scripts/github-sync.sh` が30分ごとに `git add -A` → push するため、内側に作ると
163ファイルの複製がそのまま公開されるからです。

**`git init` はしていません。** 移設時に社長が PUBLIC/PRIVATE を判断するため、
初期化コマンドは生成先の `SETUP.md` §4 手順2 に書き置きしました。

**引き継ぎメモ:** `/Users/yukinori/Claude Code/ai-company-homepage/SETUP.md`
（何を持ち出し何を捨てたか・移設後の7手順・要判断リスト・修正したパス値の一覧）

---

## 2. ファイル数の要約

| 区分 | 件数 |
|---|---:|
| **合計** | **163** |
| `agents/`（9職種 × agent.md + memory + skills） | 108 |
| `.claude/`（agents 8 / commands 5 / hooks 5 / scripts 1 / settings / launch） | 21 |
| `workspace/`（README / PROTOCOL / handover / owner-tasks / _template / .gitkeep 6） | 11 |
| `scripts/`（create-subsidiary / catalog 4 / check_source_cards / 他） | 9 |
| `docs/`（7本 + reference/web-site-build 2本のうち .md 8） | 8 |
| ルート（CLAUDE.md / README.md / SETUP.md / .gitignore / .mcp.json.example） | 4 + .gitignore |
| `_inbox_社長共有/` | 2 |

**メモリ選別: 残 69 / 元 112（43本を除外）**

| 役職 | 残 | 元 | | 役職 | 残 | 元 |
|---|---:|---:|---|---|---:|---:|
| general_affairs | 24 | 24 | | content_creator | 8 | 10 |
| it_engineer | 13 | 29 | | planner | 3 | 10 |
| legal | 8 | 17 | | secretary | 2 | 3 |
| researcher | 8 | 14 | | accounting | 2 | 4 |
| simulator | 1 | 1 | | | | |

---

## 3. 持ち出し／除外の判断根拠

### 判断の軸

**「事業が変わっても価値が変わらないか」** の1点で切りました。

- **仕組み・規律・失敗から生まれた運用ルール** → 持ち出す。事業に依存しない
- **特定のサービス・商流・商品に紐づく知識** → 捨てる。HP 制作事業では1度も使わない
- **判断に迷ったもの** → **捨てずに残し、SETUP.md §5-A の「要判断リスト」に列挙**（10件）

### 個別の判断（迷ったもの・特筆すべきもの）

| 対象 | 判断 | 根拠 |
|---|---|---|
| `docs/reference/web-site-build/` | **持ち出した**（当初の指示では `docs/reference/` は一律除外） | サイト制作の6工程プレイブック。**転用先事業の中核オペそのもの**であり、これを捨てると最も価値の高い資産を落とす。冒頭の Satoy Select 固有の注記は HP 制作事業向けに書き換え。ただし社長提供の外部資料なので、PUBLIC 運用時の第三者著作物判定を SETUP.md に要判断として明記 |
| `scripts/check_source_cards.py` | **持ち出した**（当初「物販固有なら捨てる」） | 仕組みは完全に汎用（データ置き場に SOURCE.md があるか見張るだけ）。固有なのは `RESTRICTED_SOURCES` の中身だけなので**空 dict にして移植**。移設直後は無害な no-op。クライアント支給データ・有料素材を扱い始めた時点で1行足せば効く |
| `agents/*/memory/` の Amazon 固有名詞 | **書き換えず残した** | memory は過去の判断の**記録**。後から固有名詞を消すと「いつ・何を見てそう判断したか」が失われ、記録としての価値がゼロになる。教訓が汎用でも、根拠になった事例は事例のまま残すのが正しい |
| `.claude/hooks/session-start.sh` の④⑤ | **削除**（③⑥は残す） | ④＝物販の候補リスト常時稼働ジョブ、⑤＝Amazon セラーセントラル日次チェック。どちらも実体が無い環境で毎セッション誤警告を出す。旧⑥（控え乖離検知）は guard 付きで無害なので残し、**④に採番し直した**（欠番は「④はどこ？」と探させるため） |
| `.claude/commands/new-business.md` の `amazon` プリセット | **削除** | 事業名・ミッション・KPI が全部 Amazon 物販のもの。実事業は対話モードで作る方針に統一 |
| `agents/accounting/memory/tax_invoice_menzei_seller.md` | **残した（要判断）** | 「社長＝免税事業者・インボイス未登録」は事業を跨ぐ事実。**HP 制作は B2B なので、適格請求書を出せないことがクライアントの仕入税額控除に直撃する。物販より重い論点**として SETUP.md に明記 |
| `agents/legal/` の Amazon/Keepa/NETSEA 系9本 | **削除** | 論点が丸ごと入れ替わる（古物営業法・薬機法・PSE → 著作権・素材ライセンス・権利帰属・下請法・特商法・個人情報）。`.claude/agents/legal.md` の検査観点は HP 制作向けに書き換えたが、**memory はゼロ本になったので着手前にハルオへ1本発注するよう SETUP.md で推奨** |
| `workspace/README.md` の成果物ルール | **書き換えた** | 元リポでは「最終納品物はリポ外」という**旧ルールのまま更新漏れ**していた（CLAUDE.md §6 は3層ルールに移行済み）。雛形に旧ルールを持ち込むと事故が再発するため、CLAUDE.md §6 に揃えた |
| `docs/notion-setup-guide.md` の Assignee | **修正した** | 元リポで5職種しか列挙されておらず、9職種＋owner の実態とズレていた（元リポ側の不備）。雛形では修正 |
| `agents/general_affairs/agent.md` のリンク | **修正した** | `skills/owner-tasks-summary-ownership.md` を指していたが実体は `memory/` 配下（元リポ側のリンク切れ）。雛形では修正 |

### CLAUDE.md の扱い

**§3 鉄則9つ / §4 承認ルール（4.1〜4.4）/ §5 ルーティング / §5.1 ルーティン / §6 ライフサイクル・成果物3層・inbox・Notion 同期 は、要約せず原文の精度で保持しました。**
社長が繰り返し指摘して積み上がった規律であり、削ると価値が消えるためです。

変更したのは次だけです。

- §1 を HP 制作事業に。**ミッション/KPI/主力サービス/想定顧客は社長未決定なのでプレースホルダーのまま残置**し、「移設後に社長と決める」「空のまま戦略立案を走らせると評価軸のない案が出て手戻りになる」と明記
- §4.1 の表に、HP 制作事業で発生しやすい該当例を**太字で追記**（サイトの本番公開／ドメイン・素材の購入／受注契約・見積の確定／クライアント・外注先への連絡／預かった情報の外部送信）。**判定基準そのものは変えていない**
- 固有名詞（Drive file id / Notion 実 ID / Satoy Select / Keepa / `/buppan-todo` / `/amazon_buppan_catalog`）を除去またはプレースホルダー化
- 日付入りの社長発言は、**ルールの由来として意味のあるものだけ「なぜそうなったか」の一行として残し**、事業固有の固有名詞は伏せて一般化（例：「二重管理で内容が食い違う事故」「agent_output 放置で成果物が消失」）
- §2 に「制作の実務はヒデアキとタカシにまたがる」の切り分け目安、§7 にプレースホルダー表の更新版を追加

---

## 4. 検証結果

| 項目 | 結果 |
|---|---|
| シェルスクリプト `bash -n` | 7本すべて通過（hooks 5 / github-sync / create-subsidiary） |
| フック実行スモークテスト | 5本すべて正しい JSON を返すことを確認（session-start / delegation-check / inbox-intake-check / owner-tasks-sync-check / ticket-notion-sync-reminder） |
| Python 構文 | 3本通過（check_source_cards / sync_catalog_to_sheet / md_to_standalone_html） |
| JSON パース | 4本通過（.mcp.json.example / settings.json / launch.json / notion-db-schema.json） |
| Markdown 相対リンク | 切れ **0 件** |
| 秘密情報の混入 | **なし**。`grep -rniE 'sk-\|secret\|token\|api[_-]?key\|password'` のヒットは全てプレースホルダー・変数名・「書くな」という注意書き |
| 秘密ファイルの混入 | **なし**（`.env` / `.mcp.json` / `.catalog_sync.env` / `settings.local.json` / `*.bak.*` いずれも不在） |
| 残存する Amazon 系用語 | memory/ 配下のみ（**意図的**。上記 §3 参照） |
| コピー元リポへの書き込み | **なし**（読み取りのみ。書いたのは本ファイルだけ） |

---

## 5. 社長判断が必要な論点（SETUP.md §5 の要点）

1. **リポジトリを PUBLIC にするか PRIVATE にするか** — HP 制作事業はクライアントの未公開情報・支給素材・問い合わせ経由の個人情報を扱うため **PRIVATE 推奨**
2. **`docs/reference/web-site-build/` の掲載可否** — 社長提供の外部資料。PUBLIC にするなら第三者著作物の判定が要る
3. **成果物カタログを使うか** — 使わないならコマンドとマリエの責務ごと外す（更新されないカタログは無いより悪い）
4. **インボイス（適格請求書）をどうするか** — B2B の HP 制作では、免税事業者のままだとクライアント側の仕入税額控除に直撃する。物販より重い論点
