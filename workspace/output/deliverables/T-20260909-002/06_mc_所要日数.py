import random as R
R.seed(1); N=200000; T=63  # 9/13 -> 11/15
tri=lambda a,m,b: R.triangular(a,b,m)
def B():
    d=tri(3,5,8)          # 事前チェック+下書き
    d+=tri(1,3,10)        # 社長の送信（20通）
    d+=5 if d<9 else 0    # 9/19-23 連休に掛かると返信側が止まる（簡略）
    d+=tri(3,7,21)        # 最初の前向き返信
    d+=tri(7,14,30)       # 見積・条件・口座開設
    d+=tri(5,10,30)       # 発注→出荷（在庫品〜受注生産）
    if R.random()<0.5: d+=tri(3,7,14)  # ゲートありならメーカー請求書で申請
    d+=tri(7,12,21)       # 納品代行→FBA受領・出品
    s=d+tri(1,5,20)       # 初回販売
    p=s+tri(7,14,21)      # 初回入金
    return s,p
def A():
    d=tri(3,3,5)+tri(3,5,7)          # 入口審査+発注→納品代行着荷
    d+=tri(1,1,2)+tri(3,7,14)         # 申請送信+審査(暦日)
    d+=tri(5,8,15)                    # 大口/FBA受領
    s=d+tri(1,4,15); p=s+tri(7,14,21); return s,p
for name,f in (('B',B),('A',A)):
    xs=[f() for _ in range(N)]
    ps=sorted(x[1] for x in xs); ss=sorted(x[0] for x in xs)
    print(name,'P(販売<=63)=%.2f P(入金<=63)=%.2f 入金中央=%d 80%%区間=%d-%d P(入金<=91)=%.2f'%(
      sum(s<=T for s in ss)/N, sum(p<=T for p in ps)/N, ps[N//2], ps[N//10], ps[9*N//10], sum(p<=91 for p in ps)/N))
# funnel
pa=0.40*0.70*0.70*0.50; print('A 承認まで',round(pa,3))
for n,p in ((5,.06),(8,.12),(3,.02)): print('B',n,p,round(1-(1-p)**n,3))
