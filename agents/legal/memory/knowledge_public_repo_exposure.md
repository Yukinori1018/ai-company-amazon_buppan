# ★当社の構造的リスク：リポジトリが PUBLIC である

初出：T-20260824-001（Keepa MCP 法務レビュー、2026-08-24 ハルオ）
**法務レビューのたびに必ずこの観点を通すこと。当社最大の「静かに漏れている穴」。**

## 事実

- `https://github.com/Yukinori1018/ai-company-amazon_buppan` は **PUBLIC**（`gh repo view --json visibility` で確認、2026-08-24）。
- `workspace/output/deliverables/` は Git 追跡対象であり、**成果物は直納＋即 commit が社内ルール**（feedback_deliverable_persistence）。
  → **成果物を正しく運用するほど、外に出る**という構造になっている。
- GitHub Pages は未使用（`gh api repos/.../pages` が 404）。**Private 化しても HP には影響しない。**
- 成果物カタログは GitHub blob URL を使っているが、閲覧者は所有者（社長）なので Private 化でも閲覧可。

## 現に外に出ているもの（2026-08-24 時点）

| 種類 | 例 | 法的論点 |
|---|---|---|
| Keepa 由来の商品データ 約12,000行 | `T-20260817-005/candidates_v13.csv`（約4,000行）、`T-20260803-001/shiire_list_3000.csv`（約4,400行）、`T-20260705-002/research/maker_candidates.csv`、`T-20260705-001/*.csv` | Keepa API T&C §11(1) reproduce 禁止／§2(2)(6.1(1)) 第三者提供 |
| 取引先候補の連絡先 | `T-20260804-001/contacts_batch*.json` | **個人情報保護法（第三者提供）。未精査・要別途チェック** |
| 第三者ドキュメントの全訳 | `T-20260824-001/keepa-glossary.md` | §11(1) translate 禁止 |
| 事業の内部数値・戦略 | 各種 deliverables | 競合に読まれる（法務外だが経営リスク） |

## 是正の型（A/B/C）

- **C（推奨）＝リポジトリを Private 化。** 1操作、過去履歴も含めて閉じる、**いつでも Public に戻せる（可逆）**。
- B ＝ `git rm --cached` ＋ `.gitignore`。**過去履歴は残るので抜本解決にならない。**
- A ＝ 現状維持＋今後は置かない。既存分が残る。**非推奨。**

**原則：可逆な手段で不可逆なリスクを消せる時は、迷わずそれを選ぶ。**

## 実行にあたっての制約（毎回思い出すこと）

- **Git 履歴の書き換え・ファイル削除・force push は CLAUDE.md §4.1「不可逆な削除」。法務は実行しない。**A/B/C ＋推奨まで作って秘書に返す。
- 法務自身の成果物も同じ制約下にある。**第三者文書の引用は「必要最小限＋出典明示＋自社の評価が主」（著作権法32条1項）に留め、全文複製・全訳は Git 追跡外（`agent_output/`）に置く。**自分だけ例外にしない。

---

## 追記（2026-09-06 / T-20260906-006）— PUBLIC リポを名指しで塞ぐ条項が3つ増えた

`knowledge_platform_api_data_retention.md` §4 の表に、以下を追加すること。

| サービス | 条項 | 当たる文言 |
|---|---|---|
| **楽天ウェブサービス** | Art.10(1)(9) | "Storing information obtained through the Web Services … **in a place that enables the sharing of information with unspecified and/or many people.**" |
| **LINEヤフー（Yahoo!ショッピング）** | 共通利用規約 §14 | 「当社サービスやそれらを構成するデータを、**その提供目的を超えて利用することができません**」＋**利益相当額の請求権** |
| **CAMPFIRE** | 第34条3項ただし書 | 「**プロジェクトの告知以外の目的**での紙面またはウェブ媒体等への掲載は、事前にCAMPFIREの承諾を得る」→ 仕入れ候補リストとしての公開は「告知以外の目的」 |
| **ふるさとチョイス** | 第11条1項 | 「利用者が本サイト等を利用することにより取得した情報…**許可なく転載等を行ってはならない**」 |

**新しいデータソースを見たら、必ずこの型の条項を探す。**「再配布」「第三者提供」「公衆送信」「unspecified and/or many people」「提供目的を超えて」が検索語。
