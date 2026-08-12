# 引き継ぎノート

> 別デバイス・別セッションで Claude Code を起動した際に、直前のセッションの文脈を即座に引き継ぐためのファイル。
> セッション開始時、秘書カズヨ（または任意のエージェント）はまずここを読む。
> 更新方法: `/handover` スラッシュコマンド or 手動編集。
> **次セッション開始の最も簡単な方法: `/resume` と入力するだけ**。秘書カズヨが本ファイル＋関連を自動読み込みします。

---

## 最終更新

- **日時**: 2026-08-12（AMZScout PRO AI 採否判断セッション。ナレッジ化＋A案確定＝契約せず・③OEM時に無料トライアル検証）
- **更新者**: 秘書カズヨ（ローカル）
- **次の想定読み手**: 次セッション（任意端末。`/resume` 推奨）
- **作業ブランチ**: `claude/nighttime-work-checkin-iTWEa`

### 🆕🟢 2026-08-12 セッションの引き継ぎ

- **AMZScout PRO AI 採否判断〔T-20260812-001 / done〕**: 社長共有スクショ13枚を読解しナレッジ化（memory `knowledge_amzscout_pro_ai`＝機能マップ全保存）。**社長判断＝A案で確定**＝いま契約せず、③簡易OEM〔T-20260809-001〕を具体検討する局面で**無料トライアル16回だけ**「サプライヤー画像逆引き＋AIリスティング」を検証（費用ゼロ・§4.1非該当）。見送り理由＝Keepa/ERESAと重複大・当社最優先は②メーカー仕入れでズレ・スクショは米amazon.com/USD建て。※正確な月額は未確認（B検討時にカズヨが調べる）。
- **未処理の運用課題**: 成果物カタログの**Googleスプレッド同期がWebApp HTTP 404**（`scripts/catalog/sync_catalog_to_sheet.py` のデプロイURL失効の可能性）。マスターCSVは更新済み（真実側）。次回ローカル回でシート同期をリトライ or 同期基盤の復旧チケット起票を検討。

### 🆕🟢 2026-08-11 セッションの最重要引き継ぎ（ここだけ読めば足りる）

**事業サマリ（1枚）**: `~/Documents/AI Company Outputs/Amazon物販事業/T-20260601-001/事業サマリ_方向性と進捗_2026-08-11.html`

1. **大きな方向性は4本**（社長が整理）: ①電脳せどり=**ホールド**／②メーカー仕入れ=**並走・先行(本命)**／③簡易OEM=ナレッジ蓄積／④無在庫=探索・要法務判断。**「買い候補リスト」は方向性ではなく全方向共通の作業**（枠に入れない）。
2. **共通の土台ルール（確定）**: (a) 数字は〔確定/仮/要見積り〕でタグ付けし**仮を確定として扱わない**・損益分岐点を先に出す (b) 自作より**既存・無料・既契約(Keepa/公式/無料拡張)を先に調べる** (c) **端末同期はmainを唯一の正に**（セッション毎の別ブランチ分岐が食い違いの真因。ディスパッチ設定は無関係）。
3. **②の状況**: メーカー台帳3,282社＋55社連絡先あり。本セッションで**損益分岐シミュレータ.xlsx納品**（`deliverables/T-20260804-001/`・手入力欄を色分け）。社長の実測待ち＝FBA納品代行の相見積り・送料。→ 埋まれば交渉先選定（実連絡は§4.1承認）。
4. **④の状況**: 携帯開発の**Re-Sale AutoSync**（無在庫FBM・Chrome拡張）を**mainへ統合(PR #5)**。設計/雛形は完成だが**DOMセレクタ実調整・実走テスト・本番Go判断が未了**＋**ドロップシッピングポリシー抵触リスク**残。次=法務ハルオのリスク評価（推奨A）。
5. メモリ追加: `project_strategy_multitrack_2026-08` / `feedback_research_accuracy_blocker` / `feedback_research_existing_before_build` / `project_dropship_account_health_tool`。

> ⚠️ 以下「2026-06-01」以前の記述は歴史的経緯（陳腐化あり）。最新の真実は `workspace/tickets/` と `main`。

### 🆕🔴 2026-06-01 セッションの最重要引き継ぎ（ローカルで最初にやること）

1. ~~**成果物カタログ（Googleスプレッドシート）作成 〔T-20260601-001〕**~~ → ✅ **done（2026-06-01 ローカルで完了）**
   - **Googleスプレッドシート**「成果物カタログ_Amazon物販事業」: https://docs.google.com/spreadsheets/d/1xXfKbgbbiRUns-U40sgWNUWzwvu1s2aS3Gr1Ouy5MQY/edit （社長アカウント所有・My Drive直下・12列55行/9チケット）
   - マスターCSV＝`workspace/output/deliverables/T-20260601-001/deliverables-catalog.csv`（リポ内の真実。Markdown版併置）。Drive file id=`1xXfKbgbbiRUns-U40sgWNUWzwvu1s2aS3Gr1Ouy5MQY`。
   - 既存 Drive コネクタが認証済みで **OAuthクリックすら不要**だった。マリエが棚卸し→CSV化、タカシが Drive MCP `create_file`（text/csv→Sheets自動変換）で生成。
   - 運用ルール恒久化: CLAUDE.md §6「成果物カタログ」＋庶務スキル `agents/general_affairs/skills/deliverables-catalog.md`（成果物のたびマリエが追記）。
   - **書き込み連携 〔T-20260601-003 / done〕**: Apps Script Web App 連携を整備し疎通済（2026-06-01・HTTP200/56行）。**カタログ更新は `python3 scripts/catalog/sync_catalog_to_sheet.py` 一発**で同一URLのシートを全置換ミラー更新（冪等）。手順=`scripts/catalog/README.md`、接続情報=`scripts/catalog/.catalog_sync.env`（gitignore・ローカルのみ）。クラウド回は環境変数 `WEBAPP_URL`/`SHARED_TOKEN` を渡せば実行可、無ければCSV追記までに留め次のローカル回で同期。

2. **業務フロー図 ①全体像の社長確認（確認ゲート①） 〔T-20260531-002 / doing〕**
   - 社長はまだ「大まかな全体像」を一読しただけ。②③④⑤は作成済みだが**社長レビュー未**。
   - 当初設計どおり「①全体像を確定 → その後に⑤②③④を1枚ずつレビュー」。残2本（⑩入金・会計／⑫アフターフォロー）は未着手。
   - 成果物: `workspace/output/deliverables/T-20260531-002/`（01〜05 の png＋todo.md）。

### ⚠️ handover の以下「2026-05-22〜29」記述は古い（参考情報）

- 下記の「次セッション冒頭の必須アクション」「チケット状況(2026-05-22)」「重要URL(旧ブランチ)」等は**旧ブランチ前提で陳腐化**。最新のチケット状態は `workspace/tickets/` と Notion カンバンが正。`/resume` か `/sync-notion` 不要（前セッションで全件突合済・ドリフトゼロ）。
- 直近の大きな変更: **同期破綻の復旧（幽霊チケT-027-001/002をリポジトリへ復元）／ERESA PRO 主軸へB案転換（Sato-Scope Phase2中止・Lite縮退）／業務フロー図作成**。

### 🆕 2026-05-29 の成果（T-20260529-001 / done）

- **Notion 同期の責務を秘書 → 庶務マリエに移管**。起票・移動を **PostToolUse 強制フック**（`.claude/hooks/ticket-notion-sync-reminder.sh`）が検知し、未同期で turn を終えないよう促す。実機発火確認済み。
- マリエ運用スキル `agents/general_affairs/skills/notion-ticket-sync.md` 新設（DB ID・MCP レシピ・日付/チェックボックス書式の落とし穴を集約）。
- **`/sync-notion`**（非破壊リコンサイル）新設、朝夕ルーティンに組込。
- 根本原因②=**ブランチ分岐**で Notion とリポジトリがズレる件 → 社長が **A 採択**（現状維持＋朝夕リコンサイルで自己修復、Notion 専用カード T-20260527-001/002 等は温存）。
- ⚠️ 制約：ホスト型 MCP のためシェルからの完全自動同期は不可。強制フックが最善手。

---

## ⚠️ 次セッション冒頭の必須アクション

### 1. main から新ブランチを切る

```bash
git fetch origin
git checkout main
git pull --ff-only origin main
git checkout -b claude/<次のタスク名>
```

PR #2 で旧ブランチ `claude/complete-remaining-tasks-0eCzs` の全成果物は main に統合済み。**旧ブランチは履歴保持目的で残置**（社長判断で削除可）。

### 2. 社長判断待ち事項を確認

| 件 | 社長判断 |
|---|---|
| ~~A: main マージ~~ | ✅ 完了（PR #2 マージ済、2026-05-22 夜） |
| **B: Sato-Scope Phase 2 着手** | Keepa API €49/月 課金承認（§4.1）— 先に T-004 ROI / T-005 ToS の結果を待つのが推奨 |
| **C: モック確認結果** | v0.2 モック動作確認後のフィードバック |
| **D: 4件の納品物レビュー** | T-003 ツール調査 / T-001 用語集 / T-002 シミュレーション / Sato-Scope モック |

---

## 直前セッション（2026-05-22）の締めくくり

**社長専用 Amazon 物販リサーチツール「Sato-Scope」を Phase 0 → v0.2 再設計 → Phase 1 まで完成させた**。サトル（リサーチ）／タケシ（戦略）／タカシ（IT・新設）の3者合作。

### 重要な方向転換（社長レビューを経て）

初版（Phase 0）は **Product Lookup 型**（JAN/ASIN 入力で1商品調査）で作っていたが、社長指摘で **Discovery 型**（「探す」ボタン一発で利益候補一覧）に**完全再設計**（v0.2）。

### 差別化軸の確定（D1〜D9）

| 軸 | 採用 / 不採用 | 詳細 |
|---|---|---|
| D1 仕入れ元の量 | △ 並行調査のみ | 楽天+Yahoo!固定、量拡張は社長判断後 |
| D2 マイナー公式 API | ◯ 並行調査 | 法律範囲内 |
| D3 ポイント込み実質価格 | ✅ 実装済 | トグル ON/OFF 可 |
| D4 真の利益計算（FBA/自己発送/MSS） | ✅ 実装済 | **差別化の核** |
| D5 独自おすすめスコア | ✅ 実装済 | 0〜100 スコア・デフォルトソート |
| D6 AI 解説 | ❌ 不要 | 代わりに楽天/Yahoo!/Amazon URL リンク |
| D7 中古せどり | ⏸ ペンディング | v0.x で再検討 |
| D8 コンプラ警告 | ✅ 実装済 | 11ブランド警告マスタ |
| D9 クロスチャネル裁定 | ❌ 不要 | |

### Amazon の扱い（社長指摘で整理）
- **販売データ参照元として**: ✅ Keepa 経由で売値・月販・Drop30 取得
- **仕入れ元として**: ❌ 副業初心者には不向きで除外

### Phase 1 で完成したもの（コードベース）

`workspace/output/deliverables/T-20260521-005/code/` 配下：

```
code/
├── README.md                       # セットアップ手順
├── requirements.txt / .env.example
├── app/
│   ├── main.py                     # FastAPI /search /health
│   ├── calc/
│   │   ├── profit.py               # FBA/自己発送/MSS 真の利益計算
│   │   └── score.py                # おすすめスコア + 🟢🟡🔴 判定
│   ├── compliance/brand_warnings.py # Sony/Apple/Nike 等11ブランド警告
│   ├── adapters/{keepa,rakuten,yahoo}.py # 各 API アダプタ（モック実装）
│   └── static/index.html           # モック HTML v0.2 統合済み
└── tests/test_profit.py            # ユニットテスト
```

**動作確認済み**: `/search` が 7 件抽出、Sony 警告発火、全商品で MSS > FBA を実証。

### モックの確認方法

```bash
# 方法1: HTML だけ直接開く
open workspace/output/deliverables/T-20260521-005/02_mockup.html

# 方法2: FastAPI で起動（推奨）
cd workspace/output/deliverables/T-20260521-005/code
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
# → http://localhost:8000/ でモック画面、/search で JSON、/health で稼働確認
```

---

## チケット状況（2026-05-22 最新）

| ID | タイトル | Status | 担当 | 備考 |
|---|---|---|---|---|
| **T-20260520-003** | ツール網羅調査（軸A） | waiting | researcher | 個票4本納品済、社長レビュー待ち |
| T-20260520-004 | 体験仕入れ・販売サイクル（軸B） | doing | secretary | 社長アカウント開設 |
| **T-20260520-005** | Amazon物販界隈調査 | waiting | researcher | レポートファイル所在不明・要再生成 |
| T-20260520-006 | カズくん開発ツール調査 | todo | researcher | 社長追加情報待ち |
| T-20260520-012 | 仕入れ先網羅調査（軸B 先行） | todo | researcher | サトル発注待ち |
| **T-20260521-001** | 用語集（150語×10カテゴリ） | doing | content_creator | 納品済、社長レビュー待ち |
| **T-20260521-002** | 仕入れ販売シミュレーション | doing | content_creator | 納品済、社長レビュー待ち |
| **T-20260521-003** | Ama-Jack 評価＋判断 | doing | secretary | 判断完了「無料・勧誘断る・金銭発生時退会」 |
| **T-20260521-005** | Sato-Scope 自社開発 | **doing** | it_engineer | **Phase 1 完了・Phase 2 §4.1 承認待ち** |
| T-20260521-006 | Amazak 30日後再点検 | todo | secretary | next_check_at=2026-06-20 |
| T-20260521-007 | Amazak 60日後再点検 | todo | secretary | next_check_at=2026-07-20 |
| T-20260522-001 | B2B卸API網羅調査 | todo | researcher | Sato-Scope 拡張源（社長 A1 承認） |
| T-20260522-002 | プレスリリースAPI調査 | todo | researcher | 同上 |
| T-20260522-003 | アフィリエイトASP ToS確認 | todo | legal | 同上 |
| T-20260522-004 | Sato-Scope ROI 試算 | todo | accounting | Phase 2 着手前 |
| T-20260522-005 | 公式API ToS 最終確認 | todo | legal | Phase 2 着手前 |

---

## 進行中の論点（次セッションで判断/着手すべき）

### 🔴 最優先: Sato-Scope Phase 2 着手の §4.1 承認

| 項目 | 内容 |
|---|---|
| Keepa API Power-User Plan **€49/月**（カード決済） | 必須・約¥8,200/月 |
| 楽天市場 ApplicationID 登録 | 無料・社長アカウント連動 |
| Yahoo!ショッピング ClientID 登録 | 無料・社長アカウント連動 |

社長が「Go」と言ったタイミングで Phase 2 着手。
**ROI 試算（T-20260522-004）／ToS 最終確認（T-20260522-005）の結果を待ってから判断**でも可。

### 🟡 main へのマージ可否

現在の作業はすべて `claude/complete-remaining-tasks-0eCzs` ブランチ上。main には未統合。
**社長判断**: 
- A: main にマージして本流化
- B: 現ブランチで継続（次セッションも同ブランチで作業）
- C: PR 作成して社長が GitHub 上でレビュー後マージ

推奨は **A**（本流化したい場合）または **B**（しばらく実験段階扱い）。

### 🟢 4件の納品物レビュー

社長レビュー待ち：
- T-20260520-003 ツール網羅調査
- T-20260521-001 用語集
- T-20260521-002 仕入れ販売シミュレーション
- Sato-Scope v0.2 モックの社長 PC 動作確認

---

## 重要 URL（次セッションで参照）

### Sato-Scope（T-20260521-005）

- **Notion カード**: https://www.notion.so/367b0a4044fa8185b4f0d19af0b0440b
- **GitHub (ブランチ表示)**: https://github.com/Yukinori1018/ai-company-amazon_buppan/tree/claude/complete-remaining-tasks-0eCzs/workspace/output/deliverables/T-20260521-005
- **モック v0.2 (htmlpreview)**: https://htmlpreview.github.io/?https://github.com/Yukinori1018/ai-company-amazon_buppan/blob/claude/complete-remaining-tasks-0eCzs/workspace/output/deliverables/T-20260521-005/02_mockup.html
- **code/ ディレクトリ**: https://github.com/Yukinori1018/ai-company-amazon_buppan/tree/claude/complete-remaining-tasks-0eCzs/workspace/output/deliverables/T-20260521-005/code

### 他チケットの Notion カード

- T-20260520-003 ツール調査: https://www.notion.so/366b0a4044fa81459b7ac9c36846b567
- T-20260521-001 用語集: https://www.notion.so/367b0a4044fa81259c2fc036df537583
- T-20260521-002 仕入れ販売シミュ: https://www.notion.so/367b0a4044fa81869f40dab2cdba76f7
- T-20260521-003 Ama-Jack 評価: https://www.notion.so/367b0a4044fa816ba547c1fd15b5d029
- T-20260522-001 B2B卸API調査: https://www.notion.so/367b0a4044fa8193b010c3f6c7b21e27
- T-20260522-002 PR-API 調査: https://www.notion.so/367b0a4044fa8131b4d3c0f83f31aef1
- T-20260522-003 アフィリエイトASP ToS: https://www.notion.so/367b0a4044fa818c8440ea02827e78ad
- T-20260522-004 ROI 試算: https://www.notion.so/367b0a4044fa819dbe93e840cc7f8344
- T-20260522-005 API ToS 最終確認: https://www.notion.so/367b0a4044fa81ce9f8edf1899ae40a8

---

## 社長プロファイル（毎セッション参照）

- **副業初心者**。座学より体験を優先。専門用語（SKU / FBA / カートボックス 等）が出る時は短く補足する。
- **分量のある資料はテキスト + HTML 形式で併出力**。
- 秘書とだけ対話。サブエージェントへの依頼は秘書経由。
- 結論ファースト、A/B/C＋推奨 形式の意思決定支援を好む。
- Notion カンバンで進捗を見る習慣あり。**カード本文に結果要約・アウトプット欄があると一目で把握できる**ことを評価。

---

## 直近の重要ナレッジ（memory/）

- `knowledge_dennou_sedori_system.md` — 電脳せどり「システム型物販」（朝野氏10選）
- `knowledge_buppan_consulting_session_1.md` — 48歳本業志望者へのプロコンサル（FBA/自己発送/MSS の真実、無在庫対応テクニック）

→ 物販ナレッジ１ Part3「FBA vs 自己発送 真の利益計算」が Sato-Scope の差別化の核 (D4) として実装済み。

---

## 事業の現状

- **事業名**: Amazon物販事業
- **ミッション** (CLAUDE.md §1): 「Amazon 上で利益と販売確度の高い SKU を 100 積み上げ、月商800万円・利益率20%を達成する」
- **戦略方向性**: 体験先行（軸B）で学びを蓄積してから主力カテゴリを確定
- **進行軸**: 3軸並行
  - **軸A**: 既存ツール網羅調査（T-003）— 個票4本納品済、社長レビュー待ち
  - **軸B**: 体験仕入れ・販売サイクル1周（T-004、予算上限 10万円承認済）— 社長アカウント開設中
  - **軸C**: 社長専用ツール自社開発（T-005 Sato-Scope）— Phase 1 完了

---

## 環境メモ

- **Notion カンバン DB ID**: `366b0a4044fa81788359d44b4f807458`
- **親ページ**: 「クロードコード ToDo進捗」（id `365b0a4044fa8000addbc5404f51685b`）
- **Notion DB 構成**: Assignee に `it_engineer` を**追加すべきか要確認**（現状 T-20260521-005 は secretary でカード作成済）
- **`.mcp.json`**: gitignore 対象
- **成果物の配置**:
  - Cloud セッション: `workspace/output/deliverables/<ticket_id>/`（Git 経由で PC に届く）
  - PC ローカル: `~/Documents/AI Company Outputs/Amazon物販事業/<ticket_id>/`（リポ外）

---

## 次セッション起動時の推奨初動

**最も簡単: 社長は `/resume` とだけ入力**してください。秘書カズヨが本ファイル＋ doing/waiting/todo チケット＋ Notion 状態を自動で読み込み、優先継続事項 Top 3 を提示します。

### 手動で読む場合の優先順位

1. 本ファイル（`workspace/handover.md`）の「⚠️ 次セッション冒頭の必須アクション」と「進行中の論点」
2. `workspace/tickets/doing/T-20260521-005_*.md`（Sato-Scope Phase 1 完了状態）
3. `workspace/output/deliverables/T-20260521-005/README.md`（v0.2 改訂サマリ）
4. `workspace/output/deliverables/T-20260521-005/code/README.md`（Phase 1 セットアップ手順）

### このセッションで起きた要点（時系列）

1. /resume で前回引き継ぎ確認 → Notion カードに「アウトプット欄＋URL」を追加（既存4件＋新規3件）
2. 物販ナレッジ１（朝野コンサル動画分析 .docx）を `memory/` に記録 → FBA/自己発送/MSS の真実が Sato-Scope の核に
3. T-20260521-005 Sato-Scope Phase 0 着手 → モック初版（Product Lookup 型）納品
4. 社長レビューで方向性指摘 → Discovery 型に**完全再設計**（v0.2）
5. D1〜D9 議論で質的差別化軸を確定。Amazon は販売参照のみで仕入れ元から除外
6. スクレイピング以外の合法的拡張手段を発掘（B2B卸API・プレスリリースAPI・アフィリエイトASP・公式RSS）
7. 社長 A1 承認 → 並行調査3チケット起票（T-20260522-001/002/003）
8. 社長 A 承認 → Phase 1 着手。FastAPI バックエンド一式実装、テスト全通過、`/search` で7件抽出確認
9. Phase 2 着手前の並行発注2件起票（T-20260522-004 ROI / 005 ToS）
10. handover.md フル更新（本ファイル）

すべての作業は `claude/complete-remaining-tasks-0eCzs` ブランチ上、commit `262a9da` まで push 済み。
