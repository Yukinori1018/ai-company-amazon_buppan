"""T-20260912-001 マサル 2周目: タケシ改訂版（05_mc_B一本_3波.py）の感応度。
段の所要日数・連休・アカウント事故は 05 と同一。変えたのは次の4つだけ。
  p_mult : 1社あたり成立率の倍率（0.5／1／2）。一次情報の裏付けがないため
  strict : タケシ自身の「買う」足切り（子の値は根拠にしない）を10社に当てる。
           区分3の5社は既存データで通る ASIN が0件 → 成立率0。朝倉は公開ロット20個で閾値11.1に届く ASIN が0件 → 0.5倍
  confirm: ゲートありの社で、メーカーが請求書記載を書面で確約する条件付き確率（ゲートあり50%）
  kono1  : 河野製紙（電話のみ）を波1（9/17〜18）へ繰り上げる
day0 = 2026-09-14。乱数固定。"""
import random as R, datetime as D
N=100000; day0=D.date(2026,9,14); tri=lambda a,m,b: R.triangular(a,b,m)
# (社, 送信日の範囲, 区分の成立率, strict時の倍率)
BASE=[("北陸",3,4,.06,1),("北尾",3,4,.06,1),("池本",3,4,.06,1),("朝倉",3,4,.04,.5),
      ("廣田",10,11,.04,0),("楠橋",10,11,.04,0),("田中",10,11,.04,0),
      ("大橋",15,18,.04,0),("金野",15,18,.04,0),("河野",22,25,.06,1)]
def run(p_mult=1.0,strict=False,confirm=None,kono1=False,reply=.25,seed=7):
    R.seed(seed); W=[]
    for n,a,b,p,s in BASE:
        if kono1 and n=="河野": a,b=3,4
        q=p*(s if strict else 1)
        if confirm is not None: q*= (1-.5*(1-confirm))/(1-.5*(1-.8))  # 基準を確約80%と置いて相対で振る
        W.append((a,b,q))
    got=pay_=sale_=rep=0; pays=[]; sales=[]
    for _ in range(N):
        u=R.random(); m=2.0 if u<.2 else (1.0 if u<.8 else .4); m*=p_mult
        best=bs=None; pos=0
        for a,b,p in W:
            if R.random()<min(1,reply*m): pos+=1
            if R.random()>=min(1,p*m): continue
            s=R.uniform(a,b); r=s+tri(3,7,21)+(5 if s<9 else 0); o=r+tri(7,14,30); d=o+tri(5,10,30)
            if R.random()<.5: d+=tri(3,7,14)
            d+=tri(7,12,21); sl=d+tri(1,5,20); py=sl+tri(7,14,21)
            if best is None or py<best: best,bs=py,sl
        if pos: rep+=1
        if best is not None:
            if R.random()<.08: best+=tri(30,45,90); bs+=tri(30,45,90)
            got+=1; pays.append(best); sales.append(bs)
    k=lambda dt:(dt-day0).days
    f=lambda L,dt: sum(1 for t in L if t<=k(dt))/N
    ps=sorted(pays); med=(day0+D.timedelta(days=int(ps[len(ps)//2]))) if ps else None
    return dict(成立=got/N, 返信1以上=rep/N, 販売1130=f(sales,D.date(2026,11,30)), 販売1231=f(sales,D.date(2026,12,31)),
                入金1231=f(pays,D.date(2026,12,31)), 入金0115=f(pays,D.date(2027,1,15)), 入金中央=med)
CASES=[("A0 改訂版そのまま",{}),
       ("A1 p×0.5",{"p_mult":.5}),("A2 p×2",{"p_mult":2}),
       ("B0 足切りを10社に当てる(strict)",{"strict":True}),
       ("B1 strict・p×0.5",{"strict":True,"p_mult":.5}),("B2 strict・p×2",{"strict":True,"p_mult":2}),
       ("C1 strict・確約50%",{"strict":True,"confirm":.5}),("C2 strict・確約20%",{"strict":True,"confirm":.2}),
       ("D0 strict・河野を波1へ",{"strict":True,"kono1":True}),
       ("D1 strict・河野波1・p×2",{"strict":True,"kono1":True,"p_mult":2})]
if __name__=="__main__":
    print("ケース | 1社以上成立 | 前向き返信1社以上 | 初回販売≤11/30 | 初回販売≤12/31 | 初回入金≤12/31 | 初回入金≤1/15 | 成立時の入金中央")
    for lab,kw in CASES:
        r=run(**kw)
        print(f"{lab} | {r['成立']:.0%} | {r['返信1以上']:.0%} | {r['販売1130']:.0%} | {r['販売1231']:.0%} | {r['入金1231']:.0%} | {r['入金0115']:.0%} | {r['入金中央']}")
