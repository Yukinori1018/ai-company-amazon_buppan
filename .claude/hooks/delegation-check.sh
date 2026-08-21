#!/bin/bash
# UserPromptSubmit フック：委譲チェック（抱え込み防止）
#
# 役割: 社長の依頼文に専門領域のシグナルが含まれていたら、
#       「この作業は〔担当〕です」の宣言と Agent ツールでの実発注を
#       additionalContext で促す。
#
# 背景: 秘書カズヨが専門作業を自分で抱え込む事故が3回再発した（T-20260821-001）。
#       .claude/agents/ にサブエージェントを実体登録したので、
#       「振るのを忘れる」だけが残った失敗モード。それをここで潰す。
#
# 設計:
# - ターンを絶対にブロックしない（常に exit 0。社長の手を止めない）
# - ノイズ抑制:
#     * 短文（12文字未満）・スラッシュコマンド・相槌は無音
#     * 同じ担当を連続でリマインドしない（新しい担当が現れた時 or 8分経過で再点火）
#     * キーワード無マッチ時は「長め＋依頼形」の時だけ、20分に1回の汎用リマインド
# - 状態ファイルは $TMPDIR にセッション ID で置く（リポを汚さない／セッション終了で自然消滅）

set -euo pipefail

export HOOK_INPUT="$(cat)"

MESSAGE="$(python3 - <<'PY'
import json, os, re, sys, time

try:
    data = json.loads(os.environ.get("HOOK_INPUT", ""))
except Exception:
    sys.exit(0)

prompt = (data.get("prompt") or "").strip()
session = re.sub(r'[^A-Za-z0-9_-]', '_', str(data.get("session_id") or "nosession"))[:64]

# --- 抑制①: 短文・スラッシュコマンド・相槌 ---
if len(prompt) < 12:
    sys.exit(0)
if prompt.startswith("/") or prompt.startswith("!"):
    sys.exit(0)
if re.fullmatch(r'(はい|いいえ|うん|ok|OK|了解|承知|ありがとう[ございます]*|お願いします|続けて|それで|そのまま|やって|進めて|いいよ|うんうん)[。！!?？、,.\s]*', prompt):
    sys.exit(0)

# --- 担当マップ（正規表現 → 担当名, subagent_type） ---
DOMAINS = [
    ("サトル（リサーチャー）", "researcher",
     r"調べ|調査|リサーチ|市場|競合|相場|情報収集|一次情報|ウォッチ|下調べ|比較して|どんなツール|評判|口コミ|事例"),
    ("タケシ（プランナー）", "planner",
     r"戦略|方針|計画|プラン|ロードマップ|どう攻め|カテゴリ選定|差別化|優先順位|撤退条件|積み上げ|設計方針"),
    ("マサル（シミュレーター）", "simulator",
     r"シミュレー|仮想実行|プレモーテム|シナリオ|想定して|失敗パターン|うまくいくか|予測して|リスクを洗い|最悪のケース"),
    ("ハジメ（経理）", "accounting",
     r"収支|利益|粗利|原価|仕入値|コスト|経費|予算|資金|キャッシュ|ROI|損益|採算|試算|儲か|手数料|税|申告|帳簿"),
    ("ハルオ（法務）", "legal",
     r"法務|法律|規約|契約|コンプラ|違反|適法|グレー|許可|古物|景表法|薬機|PSE|ToS|利用規約|リスク評価|訴訟"),
    ("マリエ（庶務）", "general-affairs",
     r"整理|整頓|片付け|ファイル|フォルダ|命名|アーカイブ|Notion|カンバン|同期|カタログ|一覧化|棚卸|まとめ直"),
    ("ヒデアキ（コンテンツ制作）", "content-creator",
     r"文章|ライティング|推敲|校正|清書|資料|スライド|マニュアル|手順書|説明書|コピー|記事|LP|見出し|読みやすく|ブラッシュアップ"),
    ("タカシ（IT エンジニア）", "it-engineer",
     r"スクリプト|実装|コード|プログラム|自動化|フック|hook|API|ツールを作|ツール作|バグ|デバッグ|MCP|CSV|パイプライン|リファクタ"),
]

hits = []
for label, sub, pat in DOMAINS:
    if re.search(pat, prompt, re.IGNORECASE):
        hits.append((label, sub))

# --- 抑制②: キーワード無マッチなら「長め＋依頼形」のみ、汎用リマインド ---
GENERIC = False
if not hits:
    imperative = re.search(r'(して(ください)?|してほしい|お願い|作って|やって|進めて|考えて|出して|まとめて|直して|決めて)', prompt)
    if len(prompt) >= 40 and imperative:
        GENERIC = True
    else:
        sys.exit(0)

# --- 抑制③: 連続リマインドの間引き（状態ファイル） ---
tmp = os.environ.get("TMPDIR") or "/tmp"
state = os.path.join(tmp, f"claude-delegation-check-{session}.state")

key = "GENERIC" if GENERIC else ",".join(sorted(s for _, s in hits))
now = time.time()
cooldown = 1200 if GENERIC else 480  # 汎用は20分、担当特定は8分

last_ts, last_key = 0.0, ""
try:
    with open(state, encoding="utf-8") as fh:
        raw = fh.read().strip().split("|", 1)
        last_ts = float(raw[0])
        last_key = raw[1] if len(raw) > 1 else ""
except Exception:
    pass

last_set = set(filter(None, last_key.split(",")))
now_set = set(filter(None, key.split(",")))
new_role_appeared = bool(now_set - last_set)

if not new_role_appeared and (now - last_ts) < cooldown:
    sys.exit(0)

try:
    with open(state, "w", encoding="utf-8") as fh:
        fh.write(f"{now}|{key}")
except Exception:
    pass

# --- メッセージ組み立て（1〜3行） ---
if GENERIC:
    print(
        "【委譲チェック】この依頼の担当は誰ですか？ 手を動かす前に「この作業は〔担当〕です（理由）」を1行で宣言してください（CLAUDE.md §5 着手前の可視化）。\n"
        "専門領域なら Agent ツールで実発注する（subagent_type: researcher / planner / simulator / accounting / legal / general-affairs / content-creator / it-engineer）。"
        "カズヨが自分で受けてよいのは「横断的な統合・司令塔業務・社長への報告」だけです。"
    )
else:
    cand = "、".join(f"{label} → subagent_type: {sub}" for label, sub in hits)
    print(
        f"【委譲チェック】担当候補を検知しました: {cand}\n"
        "手を動かす前に「この作業は〔担当〕です（理由）」を1行で宣言し、Agent ツールで**実発注**してください（宣言だけで自分で書き始めるのが抱え込みです / CLAUDE.md §5）。\n"
        "違う担当だと判断したなら、その理由を一言添えれば構いません。"
    )
PY
)" || exit 0

[ -z "$MESSAGE" ] && exit 0

if command -v jq >/dev/null 2>&1; then
  jq -n --arg msg "$MESSAGE" '{
    hookSpecificOutput: {
      hookEventName: "UserPromptSubmit",
      additionalContext: $msg
    }
  }'
else
  printf '%s\n' "$MESSAGE"
fi

exit 0
