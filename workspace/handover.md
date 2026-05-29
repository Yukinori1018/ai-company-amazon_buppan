# 引き継ぎノート

> 別デバイス・別セッションで Claude Code を起動した際に、直前のセッションの文脈を即座に引き継ぐためのファイル。
> セッション開始時、秘書カズヨ（または任意のエージェント）はまずここを読む。
> 更新方法: `/handover` スラッシュコマンド or 手動編集。
> **次セッション開始の最も簡単な方法: `/resume` と入力するだけ**。秘書カズヨが本ファイル＋関連を自動読み込みします。

---

## 最終更新

- **日時**: 2026-05-27（ERESA Pivot 決定）
- **更新者**: 秘書カズヨ
- **次の想定読み手**: 次セッション
- **作業ブランチ**: `claude/resume-vDg2L`

---

## 🆕 2026-05-27 重大方針転換: ERESA Pivot（B案ハイブリッド採用）

社長提供「ERESA 徹底調査レポート」を契機に、**Sato-Scope Phase 2 を中止し、ERESA PRO ¥4,980/月を主軸ツールとして導入**する B案ハイブリッド戦略を社長承認（2026-05-27）。判断は4担当（ハジメ／タケシ／タカシ／ハルオ）の合同レビューに基づく。

### 新しい構成

| 要素 | 内容 |
|---|---|
| **主軸ツール** | ERESA PRO ¥4,980/月（Keepa グラフ・詳細検索・セラーリサーチ・カート取得率・売上予測 内包）|
| **独自補完** | Sato-Scope Lite（D4 MSS／D8 コンプラ警告／D3 ポイント還元込実質価格 のみ）|
| **1年累計コスト** | ¥59,760（旧案A比 −¥50,240、3年 −¥150,720）|
| **悲観シナリオ耐性** | 月商3万でも +¥1,020/月の薄黒字（旧案Aは赤字）|

### 新規・更新チケット

- **T-20260527-001** ERESA PRO 7日無料試用→月¥4,980 契約（waiting／社長アクション待ち）
- **T-20260527-002** Sato-Scope Lite 縮退（doing／タカシに発注済、約2日）
- **T-20260521-005** 旧 Sato-Scope: Phase 2 中止、Lite 縮退に方針転換（doing 継続、Lite 完了時に done）
- **T-20260522-004** ROI: 案C' 補遺を追加（done のまま、補遺ファイル追加）

### 次セッション冒頭の最優先アクション

1. **社長から ERESA 試用開始の連絡があるか確認** → あれば T-20260527-001 を doing へ
2. **タカシの Lite 縮退作業の完了確認** → 完了していれば社長向け使い方ガイドを案内、T-20260527-002 を done へ
3. **試用申込時の確認事項**（社長に同行確認）:
   - 「ERESA AI ¥5,980」と「ERESA PRO ¥4,980」の同一性／差異
   - 7日経過時の自動課金有無
   - 月払い／年払い切替方法

### 関連ドキュメント

- 新ROI試算: `workspace/output/deliverables/T-20260522-004/addendum-eresa-pro-reassessment.md`
- 戦略 v3（タケシ）: `workspace/output/agent_output/T-20260520-003/strategy-eresa-vs-satoscope-v3.md`
- 法務チェック（ハルオ）: `workspace/output/agent_output/T-20260520-003/legal-eresa-pro-tos-check.md`
- IT 観点（タカシ）: `workspace/output/agent_output/T-20260521-005/it-perspective-eresa-pivot.md`
- ERESA レポート: メモリ `knowledge_eresa_research_report.md`

---

## 📜 以下は 2026-05-22 時点のスナップショット（参考保持）

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

## 夜間進捗

- 2026-05-29 02:00 夜間ターン: T-20260520-003 で個票 `05_delta-tracer.md` を新規納品（4本中1本目）。残: Helium 10 / Jungle Scout / セラースケット ＋ comparison v2 ＋ ハンドオフサマリ
- 2026-05-29 23:02 夜間ターン: T-20260520-003 で個票 `06_helium10.md` を新規納品（4本中2本目）。米国デファクト・AIネイティブ×API公開で中核候補だがJP単独運用は過剰投資の所見付き。残: Jungle Scout / セラースケット ＋ comparison v2 ＋ ハンドオフサマリ
- 2026-05-29 23:30 夜間ターン: T-20260520-003 で個票 `07_jungle-scout.md` を新規納品（4本中3本目）。Suite 年¥7,595/月でHelium10より約35%安、ただしAPIはProプラン階段必須・SupplierDB が独自強み・OEM志向時のみ中核候補との所見付き。残: セラースケット 1本 ＋ comparison v2 ＋ ハンドオフサマリ
- 2026-05-30 00:05 夜間ターン: T-20260520-003 で個票 `08_sellersket.md` を新規納品（4本中4本目＝**追加個票コンプリート**）。スタンダード¥2,980/プレミアム¥5,480・20日無料体験・"攻め系" 中核候補と棲み分ける "守りの中核候補" として位置づけ・物販総合研究所つながりで社長提供ナレッジと知識網一致・"軸B 月商50万円ライン到達後に検討" の条件付き候補。残: comparison v2（全8ツール）＋ ハンドオフサマリ
- 2026-05-30 00:40 夜間ターン: T-20260520-003 で **比較表 v2 `comparison-v2.md` を新規納品**（全8ツール × 10セクション：早見表／機能カバレッジ／料金（5シナリオ試算 ¥0〜¥31k/月）／JP対応／学習コスト／出力可搬性／AI連携性／役割マップ／軸B Top3／撤退条件テンプレ）。AI 連携前提で Keepa＋Helium10 を中核候補に確定、軸B 即併走 Top 3 は アマサーチ／FBA計算機／DELTA tracer。残: HTML 併出版＋ハンドオフサマリ単独ファイル
- 2026-05-30 01:10 夜間ターン: T-20260520-003 で **ハンドオフサマリ `handover-summary.md` を新規納品**（タケシ向け1段落バトン／中核データ源 vs 人手UI線引き／5シナリオ別月額試算／マサル仮想PDCA用3シナリオ前提／朝レビュー §4.1 論点5件／成果物インデックス）。残: `comparison-v2.html` 併出のみ。
- 2026-05-30 01:30 夜間ターン: T-20260520-003 で **`comparison-v2.html` を新規納品**（インラインCSS・全10セクション・横スクロール対応 table-scroll で表崩れ防止・AI連携性軸を強調タグ付き）。**夜間指示書の完了判定3項目すべてクリア**（①追加4ツール個票 ②比較表 v2（md＋html） ③ハンドオフサマリ）。朝レビューでは A）社長による粒度確認 → B）タケシへの導入タイミング戦略 A/B/C＋推奨 発注 → C）§4.1 該当（有料プラン契約は5件）を `waiting/` に切り出して社長承認、の流れを推奨。
- 2026-05-30 02:00 夜間ターン: T-20260521-002 でヒデアキが **補遺 A `addendum-scenario-c-self-fulfillment.md` を新規納品**（Scenario A=FBA vs Scenario C=完全自己発送の商品①②③個別切替試算／人件費 ¥2,000/時間×6.4h 計上で C 中央 +¥24,505 と A の +¥43,300 に対し -¥18,795 劣後／結論: 商品②猫用おやつのみ Day 60 以降に「A+ 混合運用」として自己発送切り出しテスト推奨）。残: Scenario B（FBA+MSS）の試算・playbook 本体への章組み込み・HTML 再生成。社長レビュー時は商品①最終確定（A/B/C）と古物商申請タイミングが先決事項のため、本補遺は「2周目以降の選択肢」として朝レビューでは脇に置いて差し支えなし。
