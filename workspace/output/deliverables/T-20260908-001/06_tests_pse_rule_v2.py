#!/usr/bin/env python3
"""#1 v2 の反例テスト — T-20260908-001。

━━ なぜこのファイルが要るか ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
判定文書に「〜してはならない例」を書いた時点で、それはテストケースです。
T-20260904-004 では、仕様に書いた反例を仕様自身が通していない（自分が禁じた結果を
規定どおり実装すると出してしまう）という誤りを出しました。同じことをしないため、
判定 §6 に書いた反例をすべてここに落とします。

実行:  python3 06_tests_pse_rule_v2.py
"""

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pse_rule_v2", HERE / "04_pse_rule_v2.py")
V2 = importlib.util.module_from_spec(spec)
# dataclass は cls.__module__ を sys.modules から引くため、exec 前に登録しておく
sys.modules["pse_rule_v2"] = V2
spec.loader.exec_module(V2)

FAIL = []


def check(label, got, want):
    if got != want:
        FAIL.append(f"{label}: got={got} want={want}")


def j(name, brand="サンプル社", cats=None, amazon_title=""):
    return V2.judge_pse(netsea_name=name, brand=brand, category_names=cats or [],
                        amazon_title=amazon_title)


# ── ① HARD が REVIEW より先であること（順序を崩すと危険側に化ける）──────────
# 判定 §6 の明示的な反例。光源語と家電語を両方持つ商品。
check("LED付き扇風機 → HARD", j("LED付き扇風機 リモコン付").verdict, "HARD")
check("LED付き扇風機の規則 → 1E", j("LED付き扇風機 リモコン付").rule_id, "1E")
check("充電式LEDランタン → HARD", j("充電式LEDランタン USB").verdict, "HARD")
check("充電式LEDランタンの規則 → 1B", j("充電式LEDランタン USB").rule_id, "1B")
check("LEDライト用ACアダプター → HARD", j("LEDライト用ACアダプター").rule_id, "1A")
check("並行輸入のLED電球 → HARD", j("並行輸入品 LED電球 E26").rule_id, "1C")
check("220V表記のLED投光器 → HARD", j("LED投光器 220V 屋外用").rule_id, "1D")

# ── ② REVIEW に落ちるべきもの ────────────────────────────────────────
check("LED蛍光灯 → REVIEW", j("LED蛍光灯 直管40形 昼白色 G13").verdict, "REVIEW")
check("LED蛍光灯の規則 → 1F", j("LED蛍光灯 直管40形 昼白色 G13").rule_id, "1F")
check("LED電球 → REVIEW", j("LED電球 E26 60W相当 電球色").verdict, "REVIEW")
check("シーリングライト → REVIEW", j("シーリングライト 8畳 調光").verdict, "REVIEW")
check("REVIEW は落とさない", j("LED電球 E26").blocked, False)
check("REVIEW は発注を止める", j("LED電球 E26").blocks_purchase, True)
check("REVIEW には確認文が付く", bool(j("LED電球 E26").review_note), True)

# ── ③ 1G: 光源系でメーカー不明は HARD ────────────────────────────────
check("brand空のLED電球 → HARD", j("LED電球 E26", brand="").verdict, "HARD")
check("brand空のLED電球の規則 → 1G", j("LED電球 E26", brand="").rule_id, "1G")

# ── ④ PASS: 電安法の電気用品でないもの ──────────────────────────────
check("乾電池式の掛時計 → PASS", j("掛時計 静音 電波時計").verdict, "PASS")
check("掛時計の規則 → 1H", j("掛時計 静音 電波時計").rule_id, "1H")
check("PASS は落とさない", j("掛時計 静音").blocked, False)
# ただし「充電式」が付いたら 1B に落ちる（対象外の判断を上書きする）
check("充電式の時計 → HARD", j("充電式 目覚まし時計 USB").verdict, "HARD")
check("充電式の時計の規則 → 1B", j("充電式 目覚まし時計 USB").rule_id, "1B")

# ── ⑤ 電気とまったく関係ないもの ───────────────────────────────────
check("ステンレスボウル → PASS", j("ステンレスボウル 5点セット").verdict, "PASS")
check("ステンレスボウルは規則に触れない", j("ステンレスボウル 5点セット").rule_id, "")

# ── ⑥ 記録は発火した全規則から（勝者だけに紐付けない）────────────────────
r = j("LED付き扇風機 リモコン付")
check("勝たなかった規則が残る", any(x.startswith("1F") for x in r.other_rule_hits), True)

# ── ⑦ カテゴリ名も照合対象に入る（v1 と同じ挙動を保つ）─────────────────
check("カテゴリ由来のカメラ → HARD",
      j("三脚 アルミ製", cats=["家電＆カメラ", "カメラ"]).verdict, "HARD")

# ── ⑧ 仕様の防御: 未知の verdict は異常終了する ──────────────────────
import json as _json
bad = _json.loads((HERE / "03_pse_rules_v2.json").read_text(encoding="utf-8"))
bad["rules"][0]["verdict"] = "MAYBE"
tmp = HERE / "_spec_broken_for_test.json"
tmp.write_text(_json.dumps(bad, ensure_ascii=False), encoding="utf-8")
try:
    V2.load_spec(tmp)
    FAIL.append("未知のverdictを読み飛ばした（異常終了すべき）")
except V2.SpecError:
    pass
finally:
    tmp.unlink(missing_ok=True)

if FAIL:
    print("NG")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print("OK — 全テスト通過")
