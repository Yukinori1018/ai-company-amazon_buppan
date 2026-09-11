"""T-20260912-001 タケシ改訂版: 1周目＝本丸第一陣10社・3波送信のモンテカルロ。
day0 = 2026-09-14(月)。所要の段はマサル 06_mc_所要日数.py を踏襲し、送信日だけ3波に分けた。
成立率は会社ごとの独立試行ではなく、共通の倍率（楽観/中央/悲観）を掛けて相関させる（個人事業主・実績0という共通要因）。
アカウント側の共通事故（大口切替での再認証・カナダ連動）は全社同時に止まる要因として別に置く。"""
import random as R, datetime as D
R.seed(12); N=200000
tri=lambda a,m,b: R.triangular(a,b,m)
day0=D.date(2026,9,14)
# (社, 送信日の範囲, 区分の成立率)
WAVES=[(3,4,0.06)]*4 + [(10,11,0.04)]*3 + [(15,18,0.04)]*3   # 波1=区分1＋朝倉 / 波2 / 波3(電話1社含む)
SCEN=[(0.2,2.0),(0.6,1.0),(0.2,0.4)]   # (確率, 成立率の倍率)
P_ACC=0.08                                # アカウント側の共通事故
def one():
    u=R.random(); m=SCEN[0][1] if u<.2 else (SCEN[1][1] if u<.8 else SCEN[2][1])
    best=None; order_best=None
    for a,b,p in WAVES:
        if R.random()>=p*m: continue
        s=R.uniform(a,b)
        r=s+tri(3,7,21)+(5 if s<9 else 0)       # 9/19-23 連休
        o=r+tri(7,14,30)                          # 見積・条件・口座開設 → 発注
        d=o+tri(5,10,30)                          # 出荷
        if R.random()<0.5: d+=tri(3,7,14)         # ゲートありならメーカー請求書で申請
        d+=tri(7,12,21)                           # 納品代行→FBA受領
        pay=d+tri(1,5,20)+tri(7,14,21)            # 初回販売→初回入金
        if best is None or pay<best: best=pay
        if order_best is None or o<order_best: order_best=o
    if best is not None and R.random()<P_ACC: best+=tri(30,45,90); order_best+=0
    return best, order_best
xs=[one() for _ in range(N)]
pays=[x[0] for x in xs if x[0] is not None]; ords=[x[1] for x in xs if x[1] is not None]
def by(v,L): return sum(1 for t in L if t<=v)/N
for lab,dt in [("11/15",D.date(2026,11,15)),("11/30",D.date(2026,11,30)),("12/13",D.date(2026,12,13)),("12/31",D.date(2026,12,31)),("2027/1/15",D.date(2027,1,15)),("2027/1/31",D.date(2027,1,31))]:
    k=(dt-day0).days; print(f"{lab:>10}: 初回入金 {by(k,pays):.1%}  発注 {by(k,ords):.1%}")
print("1社以上成立", f"{len(pays)/N:.1%}")
ps=sorted(pays); q=lambda f: day0+D.timedelta(days=int(ps[int(len(ps)*f)]))
print("成立時の初回入金 中央", q(.5), "80%区間", q(.1), "〜", q(.9), "最短", day0+D.timedelta(days=int(ps[0])))
os_=sorted(ords); print("成立時の発注 中央", day0+D.timedelta(days=int(os_[len(os_)//2])))
for lab,m in (("楽観",2.0),("中央",1.0),("悲観",0.4)):
    q0=1
    for a,b,p in WAVES: q0*=1-p*m
    print(lab,"1社以上成立",f"{1-q0:.0%}")

# ---- 第2陣を足した場合（B-X1: 10/16 時点で前向き返信が2社未満なら、10/19〜23 に第2陣10社を送る）----
print("\n--- 第2陣込み ---")
R.seed(34)
REPLY=0.25   # 1社あたり前向き返信率（中央）。成立率はその内数
def two():
    u=R.random(); m=2.0 if u<.2 else (1.0 if u<.8 else 0.4)
    best=None; pos=0
    for a,b,p in WAVES:
        s=R.uniform(a,b)
        if R.random()<min(1,REPLY*m) and s+tri(3,7,21)+(5 if s<9 else 0)<=32: pos+=1
        if R.random()>=p*m: continue
        r=s+tri(3,7,21)+(5 if s<9 else 0); o=r+tri(7,14,30); d=o+tri(5,10,30)
        if R.random()<0.5: d+=tri(3,7,14)
        d+=tri(7,12,21); pay=d+tri(1,5,20)+tri(7,14,21)
        best=pay if best is None else min(best,pay)
    if pos<2:
        for _ in range(10):
            if R.random()>=0.03*m: continue
            s=R.uniform(35,39); r=s+tri(3,7,21); o=r+tri(7,14,30); d=o+tri(5,10,30)
            if R.random()<0.5: d+=tri(3,7,14)
            d+=tri(7,12,21); pay=d+tri(1,5,20)+tri(7,14,21)
            best=pay if best is None else min(best,pay)
    if best is not None and R.random()<P_ACC: best+=tri(30,45,90)
    return best
ys=[two() for _ in range(N)]; ys2=[y for y in ys if y is not None]
for lab,dt in [("12/31",D.date(2026,12,31)),("2027/1/15",D.date(2027,1,15)),("2027/2/15",D.date(2027,2,15))]:
    k=(dt-day0).days; print(f"{lab:>10}: 初回入金 {sum(1 for t in ys2 if t<=k)/N:.1%}")
print("1社以上成立（第2陣込み）", f"{len(ys2)/N:.1%}")
