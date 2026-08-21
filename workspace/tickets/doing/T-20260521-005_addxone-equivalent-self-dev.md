---
ticket_id: T-20260521-005
title: ADD×ONE PROJECT 同等の社長専用 物販リサーチツール 自社開発検討
status: doing
assignee: it_engineer
priority: high
created_at: 2026-05-21
updated_at: 2026-06-09
next_check_at: 2026-09-10
requires_approval: true
labels: [dev, research, mvp, tooling]
related_tickets: [T-20260520-006]
---

## 要件

社長依頼: ADD×ONE PROJECT（物販ONE グループ独自開発、150万円コース付属推定）と同等の **社長専用** Amazon 物販リサーチツールを自社で作れないかの検討。

> 「できれば、私専用で私しか使わないので、簡易的な同じような役割を持ったアプリないしWebアプリないしWebサイトを作ることはできないでしょうか」 — 社長 2026-05-21

## 機能イメージ（ADD×ONE PROJECT 観察より）

- カテゴリ別検索プリセット（ADD×ONE では「宝の地図1〜15」）
- Keepa API 連携で Amazon 側データ取得
- 価格比較サイト（Yahoo!ショッピング 等）から仕入候補取得
- 利益計算 + 判定フラグ（原石／あやしい／はずれ）
- 結果テーブル: ASIN / タイトル / 売値 / 仕入値 / 利益 / 利益率 / 月販 / Drop30 / 仕入元

## 想定構成案（暫定）

| 構成要素 | 案 |
|---|---|
| バックエンド | Python (FastAPI) + SQLite |
| フロント | 最小 Web UI（社長専用・ベーシック認証） |
| Amazon データ | **Keepa 公式 API**（€49/月） |
| Yahoo!ショッピング | **公式 Web サービス API**（無料枠あり、ToS 安全） |
| 利益判定 | 売値 × Keepa 推定 × 仕入値 × FBA手数料 → 原石/あやしい/はずれ |
| ホスティング | Vercel / Railway 等（月数百円） |
| 月額ランニング | 約 9,000〜10,000円（Keepa 主） |

ADD×ONE はスクレイピング方式と推定だが、本案は **Yahoo!公式 API を使うため ToS 違反リスクなし** が法務観点の優位。

## §4.1 該当事項（社長承認必須）

1. **IT エージェント新規雇用**（agents/it_engineer/agent.md 整備、CLAUDE.md §2 追記）= 仕組みの追加
2. **開発時間コスト発生**（AI 側）
3. Keepa API 課金（€49/月＝約9,000円）= 月額サブスク追加

## タスク分解（社長承認 A 取得後の想定）

- [ ] A/B/C の社長判断（**A 推奨: IT エージェント「タカシ」雇用**）
- [ ] A の場合: `agents/it_engineer/agent.md` 起票・CLAUDE.md §2 追記
- [ ] 経理ハジメ並列発注: 開発・運用コスト試算と ROI 評価
- [ ] 法務ハルオ並列発注: Keepa API + Yahoo!公式 API + Amazon ToS の整合確認
- [ ] IT タカシ（or 代替）: MVP 設計 → 実装 → 社長確認
- [ ] コンテンツ制作ヒデアキ: 社長向け使い方マニュアル

## 社長判断ポイント（A/B/C）

- **A（秘書推奨）**: IT エージェント「タカシ」新規雇用。MVP 開発を担当
- **B**: 既存エージェント（経理＋庶務）で代替対応（精度・速度落ちる）
- **C**: 外注検討（コスト・契約発生で §4.1 案件に）

## 現在地

**Phase 0 完了**（2026-05-22）。サトル・タケシ・タカシ3者合作で以下を納品、社長レビュー待ち。

- `workspace/output/deliverables/T-20260521-005/01_tool-overview.md` — ツール概要・MVP仕様
- `workspace/output/deliverables/T-20260521-005/02_mockup.html` — HTML モック
- `workspace/output/deliverables/T-20260521-005/03_research-and-strategy.md` — リサーチ＆戦略ログ
- `workspace/output/deliverables/T-20260521-005/README.md`

A/B/C 判断後に Phase 1（API 接続検証）着手。Phase 1 時点で Keepa API €49/月課金の §4.1 承認を改めて取得。

## ログ

- 2026-05-21 起票。社長依頼受領 → A/B/C 提案
- 2026-05-21 社長 A 承認（IT エージェント「タカシ」新規雇用で進行）
- 2026-05-22 タカシ正式登用（`agents/it_engineer/agent.md` 作成、CLAUDE.md §2/§5 追記）
- 2026-05-22 Phase 0 納品。3者合作で概要・モック・戦略ログを deliverables 配置
- 2026-05-22 社長レビューで方向性指摘（「商品決まっている前提か？」） → 完全方向転換。Product Lookup 型 → **Discovery 型**へ
- 2026-05-22 D1〜D9 議論を経て差別化軸を質的方向（D3/D4/D5/D6/D8）に確定。Amazon は販売参照のみで仕入れ元から除外
- 2026-05-22 **モック v0.2 を Discovery 型に書き換え**。8件サンプル・ソート/フィルター/ポイント込み価格トグル/★お気に入りが実動
- 2026-05-22 並行調査 3 チケット起票（T-20260522-001 B2B卸API/002 PR-API/003 アフィリエイトASP-ToS）。A1 承認に基づき走らせるが実装は社長判断待ち
- 2026-05-22 社長 A 承認 → **Phase 1 着手**。タカシがコードベース構築：
  - `code/app/calc/profit.py`（FBA/自己発送/MSS 真の利益計算）+ ユニットテスト全通過
  - `code/app/calc/score.py`（おすすめスコア + 🟢🟡🔴 判定）
  - `code/app/compliance/brand_warnings.py`（Sony/Apple/Nike 等の警告マスタ）
  - `code/app/adapters/{keepa,rakuten,yahoo}.py`（モック実装、Phase 2 で実 API 接続）
  - `code/app/main.py`（FastAPI /search /health エンドポイント）
  - 動作確認: `/search` が 7 件抽出、スコア降順、Sony 警告も発火
- 2026-05-22 Phase 2 着手前の並行発注 2 チケット起票:
  - T-20260522-004 Sato-Scope ROI 試算（ハジメ）
  - T-20260522-005 公式 API ToS 最終確認（ハルオ）
- 2026-05-22 Phase 2 着手の §4.1 承認待ち（Keepa €49/月 + 楽天/Yahoo! ApplicationID 登録）
- 2026-05-22 **社長レビューでモック OK、Phase 2 即 GO 承認取得**。Keepa Power-User Plan €49/月 課金 §4.1 承認確定。次は社長手作業で Keepa 申込＋楽天 ApplicationID＋Yahoo! ClientID 取得（カズヨが手順書を提示）
- 2026-05-25 ハジメ ROI 試算完了（案A 自社開発が回収最有利・1.0ヶ月）。サトル/ハジメ共通論点「軸B 0周問題」浮上
- 2026-05-25 **社長指摘で重要訂正: Sato-Scope と ERESA は代替でなく補完（別レイヤー）**。Sato-Scope は仕入れ発見を担う唯一の自社資産で置換不可。「ERESA で代替＝不要」論を取り下げ。memory に記録（`agents/secretary/memory/knowledge_satoscope-vs-eresa-different-layers.md`）
- 2026-05-25 **社長方針確定（選択肢1）: Phase 2 継続 GO ＋ 軸B 1周を最優先 ＋ ERESA は保留**。API キー取得は社長手作業待ち。next_check_at を 2026-05-26 に更新
- 2026-05-27 社長手作業（API キー取得）のボトルネック解消のため、カズヨが取得手順書を先回り作成・納品（`04_api-key-setup-guide.md`）。Keepa(€49/月・承認済)/楽天/Yahoo! の3キー取得〜`.env`設定〜`/health`でlive確認までを初心者向けに記載。社長のキー取得待ち継続、next_check_at を 2026-05-28 に更新
- 2026-05-27 **B案ハイブリッド方針転換**: Phase 2 自社開発を中止し ERESA PRO 主軸へ（T-20260527-001/002 起票）。Sato-Scope は独自2軸のみ Lite 縮退
- 2026-05-29 waiting へ移動（新基準＝社長タスク一覧化）
- 2026-06-01 ブランチ統合（resume-vDg2L）でログ統合。next_check_at を 2026-06-02 に更新
- 2026-06-04 **社長依頼で再起動**: 「Amazonで利益が出る商品をAIで調べるツール/システムを開発してほしい」。同日 NETSEA で10社以上の卸取引承認を取得（軸B実弾化）。ツールを2層に再整理し doing へ。
  - **第1層=利益判定エンジン（無料・承認不要）をタカシが新規実装＝本日完成**:
    `code/calc/profit.py`（UI分離の純ロジック）/`code/calc/fees.py`（料率・FBA定数表＝要・経理検証マーク付）/`code/calc/test_profit.py`（pytest 9件オールパス）/`code/adapters/keepa.py`（第2層スタブ）/`app.py`（Streamlit単品＋複数判定UI）/README/requirements.txt。deliverables/T-20260521-005/code/ に確定保存。
    動作確認例: 卸1,000円→Amazon2,980円(ホーム&キッチン/標準1/送料200)=純利益849円・利益率28.5%・判定「原石」🟢。
  - 第1層はNETSEA卸×ERESA手動参照と即補完可能（社長が数字を入れれば仕入可否を判定）。月額0円。
  - 経理ハジメに料率/FBA手数料の検証を並行発注（§4.2 自律）→ **符号反転しうる誤りを発見**（toys/sports料率15%→10%・最低手数料30円欠落・FBA 2025/4改定値未反映）。レポート=`05_fee-verification-by-accounting.md`。タカシが確定分を即修正（fees.py）→ **pytest 17件パス・判定符号は不変**（FBA値下げ分だけ利益改善: 卸1,000→Amazon2,980の純利益 849→965円）。health/apparel/food料率・large_1区分は **要・社長Seller Central確認**マークで残置。
  - **第2層=Amazon自動取得（AIが自動で儲かる商品を探す）はKeepa €49/月が必要 → §4.1。** 2026-05-22に一度承認→05-27にERESA主軸へ転換した経緯あり。今回の「自動探索」依頼で再判断が必要。A/B/Cで社長に提示。

  - 2026-06-04 **社長が B（自動化フル）を選択し実行**。Yahoo APP ID取得→接続→本物の仕入れ候補表示を社長が画面で体感。「基準は？」の問いから"Amazon側が無いと選別不可"を実感し**Keepa €49/月を承認・即契約**（20tokens/min・domain5）。
  - 2026-06-04 **Keepa接続完了＝(い)仕入れ元起点モード本番稼働＝ツール完成**。タカシがKeepaBackend実装（BuyBox優先/月販monthlySold/出品者数/在庫切れ率/トークン上限10件）。「水筒」実走でJAN16件中10件照会→9件Amazonヒット→**実利益ランキング**（サーモス2L 仕入4,380→Amazon9,500=純利益3,181円/33.5%/月販28 等）。pytest 29件パス。鍵は.env(git対象外)。
  - 既知の限界: (あ)Amazon起点モード未実装（Keepa Product Finder要）／FBAサイズ・月販は一部推定／相場変動は出品前再確認／料率は要・経理ハジメ継続検証。
  - 2026-06-06 **重大な誤突合バグを修正＋カズヨ実データ検証**。社長指摘「仕入元商品とAmazon商品が全く別物」（例:Yahoo滑り台JAN4580502099086→Amazon物置/ジャングルジムJAN4580502265306→デスク）。原因確定: JAN突合自体は正しいが**Yahoo出店者が誤った/使い回しJANを登録**（安い輸入雑貨で頻発のデータ品質問題）＋resolve_manyの位置フォールバックがJAN不一致商品を順番で無理やり割当。タカシ修正: (1)位置フォールバック撤去＝eanList/upcListに当該JANが実在する商品だけ確定マッチ (2)別商品検知ガード新設discovery/name_match.py＝仕入元名とAmazon名がかけ離れた組は利益ランキングから除外し「⚠️JAN誤登録の疑い」セクションに両名併記 (3)数量フラグ矛盾修正(?/?なのに数量一致)。pytest 123件パス。カズヨがPreview/実走で検証: 遊具→物置・デスク誤突合がランキングから消失（正しい商品のみ・赤字ではずれ表示=正直挙動）、耳栓→MOLDEX純利益1,506円原石🟢が正しく残存。**学び再確認: 遊具/大型おもちゃはJAN汚染＋安売りで儲からない／小物雑貨(耳栓等)が原石頻出**。
  - 2026-06-05 **UX改善（社長指摘: (あ)モードに入力欄無し＋カテゴリ少なすぎ）**。カズヨがPreview MCPで実画面確認し裏取り。タカシ修正: 探索カテゴリ5→16(Keepa /category APIでco.jpルートID実取得・出典コメント付き: drugstore160384011/beauty52374051/food57239051/appliances3210981/pc2127209051/diy_tools2016929051/baby/car/hobby/instruments/industrial 等)／モードUX刷新(🔍(い)キーワードで探す=初心者既定で先頭・🪄(あ)カテゴリから自動・📈(あ旧)売れ筋、1行ヘルプ＋キーワード欄を最上部に)／判定説明文をpreset実値から動的生成(active_gem_criteria_text)。**隠れ重大バグ修正: presetを8%/300に緩めてもprofit.calculateが既定15%/500で判定し緩和が無効化されていた→pipelineの全ProfitInputにpreset閾値を渡して連動**。pytest 108件パス。Preview実画面で16カテゴリ・キーワード欄・🟢Keepa接続中表示を確認。
  - 2026-06-05 **原石0件問題を修正＋実原石を実データ確認**。社長フィードバック「原石が全然出てこない」。診断: (1)「Keepaオフライン」はUI誤表示（実は接続中）(2)真因＝突合できた行まで`_passes_amazon_filters`/`_apply_profit_filters`が"条件外"で削除し0件化＋単品vs単品を一律「数量要確認」降格で原石が永遠に付かない設計。タカシ修正: 突合行は捨てず全件返し原石🟢/あやしい🟡/要確認ラベル付与・利益閾値はバッジ付与条件に限定／原石基準を初心者既定に緩和(利益率8%・純利益300円)／Yahoo最大60件ページング＋楽天併用でJAN母数拡大／バナー修正(🟢Keepa接続中・残トークン表示)。pytest 104件パス。実走で原石実例: 耳栓MOLDEX 仕入560→Amazon3,200=純利益1,886円/59%🟢・モルデックスMeteors 760→3,000=1,506円/50%🟢。**学び: 水筒/タンブラーはAmazon安売りで原石出にくい／耳栓・爪切り等の小物雑貨が原石頻出**。キーワード選定が歩留まりを左右。
  - 2026-06-05 **楽天市場API 本番稼働（仕入れ先②追加・無料）**。社長が楽天デベロッパー新ポータルで App ID/Access Key 取得→「許可するWebサイト」に `github.com` 登録。当初403（Origin門番が登録値と不一致）でタカシが実験的に解明：真の門番は`Origin`ヘッダで登録ドメインと**ホスト完全一致**（www有無で別物・scheme/末尾スラッシュは不問）。`.env`に`RAKUTEN_REFERER=https://github.com`確定。「水筒」実走でサーモス2Lジャグ4,180円等の実商品取得を確認。pytest 14件パス。adapters/{rakuten_shopping,multi_supplier}.py で Yahoo＋楽天をマージし同一JANは最安仕入れ先を自動選択→**原石歩留まり向上**。学びは agents/it_engineer/memory/rakuten_new_api_referer_gatekeeper.md。

  - 2026-06-09 **社長依頼でPoiPoiポケット式に改良着手**（共有docx『PoiPoiポケットを活用した自動化せどり戦略』を分析）。「ほぼ同じ機能・レイアウト」を目標に doing へ。カズヨがKeepa仕様を整理し方針確定:
    - **Phase2のURL貼り付けは技術的に必須でない**（現アプリは既にKeepa API `/query` selectionで入口Aを使用＝条件はアプリ側で組み立て済）。PoiPoiがURL貼付なのはPoiPoi側に条件作成UIが無いため。
    - 方針: **入口A（スライダーで5条件を組む）を主役にし、URL貼り付けは上級者向け折りたたみオプションで両立**（社長の自動Discovery志向に合わせる）。
    - レイアウト: 社長承認で **PoiPoi風3フェーズ縦並び（①抽出条件→②取り込み/実行→③絞り込み&最終判断）に全面改修**。
    - 実装差分4点をタカシ発注: (1)Phase1プリセットをPoiPoi基準(出品者数≥2/価格≥3000/在庫切れ/ランク5万-15万)に整備 (2)Keepa検索URL貼付パーサ(任意) (3)抽出後の動的フィルタ(利益額/月販/利益率レンジ・低リスク版) (4)Keepa価格推移グラフ＋最悪相場シミュレーション(過去相場まで下落しても黒字か=損切り回避判定)。
    - **実装完了(タカシ)・カズヨPreview検証済**: 3フェーズ縦並びUI / PoiPoi標準プリセット / 動的フィルタ＋低リスク版ボタン / 最悪相場シミュレーション / Keepa URL貼付。pytest 178件パス・画面エラーなし。commit 1bf015a。
  - 2026-06-09 **社長指示「初心者向け・上級者向けで分けるのはやめて」→ スキルレベル区分を画面から全撤廃**（タカシ実装・カズヨ検証）。内部key(*_beginner)は不変、画面文言のみ修正: モード選択肢「(上級者向け)」削除／Keepa URL貼付expanderを「(任意)」化／プリセットlabelを"絞り込みの強さ・狙い"へ(例「価格差ハンティング(推奨)」「同・しっかり絞る」「高利益率重視(少数精鋭)」「原石オートサーチ(推奨)」)／旧ヘルプ「標準→初心者に緩めて」(方向逆転バグ)を方向非依存に是正。pytest 178件パス。Previewで5ラジオ・全画面にスキルレベル語ゼロを確認。社長就寝中の自走で完遂。

## 社長判断待ち（2026-06-04 更新）

**🎉 ツール完成（(い)モード本番稼働）。社長アクション＝実際に使ってフィードバック。**
- 起動: `cd workspace/output/agent_output/T-20260521-005/code && python3 -m streamlit run app_discovery.py` →(い)モードで「水筒」等を検索→実利益ランキング確認。
- 次の発展候補（社長の感触次第・要相談）: (あ)Amazon起点モード実装／楽天API追加（無料）／プリセット調整／NETSEA卸の手動投入対応。
- 2026-08-21 棚卸し（マリエ／T-20260821-007）: next_check_at 2026-06-10 → 2026-09-10 に再設定。仕分け=A。理由: Sato-Scope の親。子は生きているが、実利はKeepa API直運用で出ており優先度は下がる
