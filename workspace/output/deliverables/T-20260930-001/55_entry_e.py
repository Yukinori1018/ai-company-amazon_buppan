"""入口(e)：売価1,500円以上のまま、大カテゴリーランクを 50,001〜100,000位 に広げてメーカー候補を足す
（T-20260930-001 / タカシ 2026-10-19 夜間）。

なぜ：12_窓口集めキュー.csv は入口(d)（売価1,250〜1,499）の分まで 5,051位で尽きる。
次に動かす条件は「売価をさらに下げる（1,000〜1,249）」ではなく「ランクの上限 50,000」にした（秘書判断）。
- メーカー直は単価が低いほど掛け率で利益が出ない（6掛けでは利益率20%不可・単価下限 2,200/3,900円の試算）
- 1,001〜1,100円は販売手数料・FBA の死に帯（CLAUDE.md §3.3-23）
- 入口(d) の歩留まりは低かった（ZR 85行で接触候補2社）。売価を下げ続けるより、売価の高い棚を深く掘る

変えたもの（1変数だけ）：大カテゴリーランクの帯を 50,001〜300,000 に（帯 rank）。帯 price は下の BANDS を参照。売価は 1,500円以上（上限なし）、カートの FBA／自己発送は問わない。
変えていないもの：monthlySold ≥ 50（積極条件）・本体の365日在庫切れ率 ≥ 90%・FBA 出品者の条件・一次除外・本人カート疑い・規模・上場。
ランク 5万〜10万は CLAUDE.md §3.3-8 の「10万位以内で PASS」の内側。月販≥50 の実売条件は外していない。

追加の修正（ZR の担当の指摘）：「層5 大手」を Keepa のブランド欄だけで決めていたため、ブランド欄が誤っている棚で中小が大手に紛れた
（5035 イケヒコ→実はグリーンベル、5036 ヤマト→実はピエラス。どちらも manufacturer 欄は空、商品名にその社名が無い）。
入口(e) では大手判定（層5・一次除外の大手）に big_verify() の裏付けを要求し、取れない社は層3（規模不明）に回して「要確認」に理由を書く。

    python3 55_entry_e.py list  [--band rank|price]
    python3 55_entry_e.py fetch --until 05:15 [--band ...]
    python3 55_entry_e.py build --until 06:30 [--band ...] [--dry-run]
    再実行は冪等：キャッシュ済みは0 token、キューに入った社は層の印「（入口e …）」で二重に増えない。
    キューへは追記のみ（既存行は書き換えない）。

出力（agent_output/T-20260930-001/・Keepa 加工値を含むので Git 除外）
  11f_追加候補_入口e.csv / 12g_入口e_落とした行.csv / 12_窓口集めキュー.csv（.bak_entrye_<日時> に退避）/ entry_e_status.json
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("entry_b", HERE / "52_entry_b.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)
R = M.R

# 社名の部品のうち、それだけでは社を特定しない語（商品名に出ても裏付けにしない）
GENERIC = {"コーポレーション", "ジャパン", "japan", "corporation", "corp", "inc", "co", "ltd", "jp",
           "工業", "製作所", "商事", "産業", "化学", "製薬", "販売", "商会", "本舗", "グループ", "ホールディングス"}


def _parts(name: str) -> list[str]:
    name = R.CORP.sub("", name or "")
    return [x for x in R.bb._parts(name) if len(x) >= 2 and x not in GENERIC]


def big_verify(p: dict, items: list[dict]) -> str:
    """大手判定の裏付け。取れれば ""、取れなければ理由。
    裏付け＝(1) manufacturer 欄がブランド欄と別に入っている（2欄が独立に社を指す）、
    (2) ブランド欄だけのとき、その社の商品名のどれかに社名の部品が出る、のいずれか。"""
    brand = (p.get("brand") or "").strip()
    maker = (p.get("manufacturer") or "").strip()
    nb, nm = R._n(R.CORP.sub("", brand)), R._n(R.CORP.sub("", maker))
    # manufacturer 欄がブランド欄と別に入っていれば、2つの欄が独立に社を指している＝ブランド欄だけの判定ではない。
    # （初版は manufacturer 欄も商品名と突き合わせたが、J-オイルミルズ／Generic・ユニチャーム／unicharm の
    #   本物の大手を層3 に落とした。ZR で見つかった誤りは2件とも manufacturer 欄が空だったので、そこに絞る）
    if nm and nm != nb:
        return ""
    titles = [R._n(x.get("title") or "") for x in items]
    for part in _parts(brand):
        if any(part in t for t in titles):
            return ""
    return f"manufacturer 欄が空で、ブランド欄「{brand}」が商品名に出ない"


# 帯は2本。どちらも「入口(e)」で、層の印で分かれる。--band で選ぶ（既定 rank）。状態は entry_e_status.json の帯ごとのキーに書く
#   rank  … ランク 50,001〜300,000・売価 ≥1,500（秘書の第一候補。Finder 2026-10-19 で一覧 50,001〜100,000 は 694件・新規288件、
#            100,001〜300,000 は 85件しかない＝月販≥50 とランクは強く相関していて、ランク軸はすぐ尽きる）
#   price … ランク ≤50,000・売価 1,000〜1,249（rank 帯だけでは少なすぎるため §3.1 で併用。Finder 2,506件）。
#            1,001〜1,100円は FBA 配送代行が1段上がる死に帯（§3.3-23）なので層の印のあとに「・死に帯」と付ける
BANDS = {
    "rank": dict(tag="wideE", rank=(50_001, 300_000), price=(1_500, None),
                 label="入口(e) ランク5万〜30万・売価1,500以上", mark="（入口e ランク5万〜30万）",
                 cand="11f_追加候補_入口e_rank.csv", drop="12g_入口e_rank_落とした行.csv"),
    "price": dict(tag="wideE2", rank=(1, 50_000), price=(1_000, 1_249),
                  label="入口(e) 売価1,000〜1,249", mark="（入口e 売価1,000〜1,249）",
                  cand="11f_追加候補_入口e_price.csv", drop="12g_入口e_price_落とした行.csv"),
}
band = "rank"
if "--band" in sys.argv:
    j = sys.argv.index("--band"); band = sys.argv[j + 1]; del sys.argv[j:j + 2]
B_ = BANDS[band]
(lo, hi), (plo, phi) = B_["rank"], B_["price"]
M.TAG = B_["tag"]
M.ORDER = M.keepa_io.RAW / f"order_{B_['tag']}.json"
M.STATUS = M.WORK / "entry_e_status.json"
M.PRICE_MIN_B = plo
M.SEL_B = {**{k: v for k, v in M.E["WIDE_A"].items() if k != "buyBoxIsFBA"},
           "current_SALES_gte": lo, "current_SALES_lte": hi, "current_NEW_gte": plo}
if phi:
    M.SEL_B["current_NEW_lte"] = phi
M.RANK_RANGE = (lo, hi)
M.BIG_VERIFY = big_verify
M.LAYER_NOTE = (lambda r: "・死に帯" if 1_001 <= float(r["代表の売価"] or 0) <= 1_100 else "") if band == "price" else None
M.LABEL, M.ENTRY_MARK = B_["label"], B_["mark"]
M.KNOWN_ORDERS = ("order.json", "order_wideA.json", "order_seller.json", "order_wideB.json", "order_wideC.json",
                  "order_wideD.json") + (("order_wideE.json",) if band == "price" else ())
M.OLD_POOLS = [("order_wideB.json", "wideB"), ("order_wideC.json", "wideC"), ("order_wideD.json", "wideD")]
M.OUT_CAND, M.OUT_DROP, M.BAK_TAG = B_["cand"], B_["drop"], f"entrye_{band}"
M.RESERVE = 0  # 2026-10-19 夜は他の Keepa 利用なし（秘書確認）


def _status(**kw) -> None:  # 帯ごとのキーに書く（2本が同じファイルで上書きし合わないように）
    p = M.STATUS
    s = json.loads(p.read_text()) if p.exists() else {}
    s.setdefault(band, {}).update(kw)
    s[band]["更新"] = datetime.now().isoformat(timespec="minutes")
    p.write_text(json.dumps(s, ensure_ascii=False, indent=1))


M.status = _status

if __name__ == "__main__":
    M.main()
