# ゲート一括確認（ブラウザ・同一オリジン iframe）

2026-10-09 にカズヨが確立した手順。**43 ASIN を人手ゼロで判定できる。**

## なぜ fetch ではだめか
`/hz/approvalrequest/restrictions/approve` は **クライアント描画（SPA）** で、`fetch()` で取った HTML には
i18n の JSON しか入っていない。**素の fetch で判定すると、i18n の文字列に誤ヒットして嘘の結果が出る**
（実際に1回出した）。**同一オリジンの iframe に読ませて `innerText` を読む**のが正。

## 判定の規則（2026-10-09 実測・N=44）
「受け付けていません」のリストに **`その他の商品`** が入っていたら **新品で出品できない**。それ以外は可。

- `その他の商品` … 新品を含む通常の出品が不可。**書類を揃えても無駄**
- `再生品のコンディションの…` `コレクター商品のコンディションの…` `中古, 再生品, …` … **新品には関係ない**。これで不可と読まない
- `この商品は以下のコンディションで販売できます：新品` の行は、**出品許可の対象だったときだけ**出る。
  制限が元から無い ASIN では出ない。**この行の有無で判定しない**

## 手順
セラーセントラルのいずれかのページを開いたタブで `javascript_tool` から実行する。

```js
window.__gc = async function(list){
  const f=document.createElement('iframe');
  f.style.cssText='position:fixed;left:-9999px;width:1200px;height:900px';
  document.body.appendChild(f);
  const out=[];
  for(const a of list){
    f.src=`/hz/approvalrequest/restrictions/approve?asin=${a}&itemcondition=New`;
    await new Promise(r=>{f.onload=r; setTimeout(r,6000);});
    await new Promise(r=>setTimeout(r,1500));
    let t='';
    try{ t=(f.contentDocument.body.innerText||'').replace(/\s+/g,' '); }catch(e){ out.push(a+'|ERR'); continue; }
    const i=t.indexOf('出品申請 ');
    const body=i>=0? t.slice(i+5, t.indexOf('サイトマップ', i)) : '';
    const blk=(body.split(/受け付けていません/)[1]||'');
    out.push(a+'|'+(blk.includes('その他の商品')?'NG':'OK'));
  }
  f.remove();
  return out.join(' , ');
};
await window.__gc(["ASIN1","ASIN2"]);
```

**1回あたり7〜8 ASIN まで**（JS の実行時間制限に当たるため）。1 ASIN 約3.5秒。

## 注意
- ブランド型ゲートを解除すると結果が変わる。**ブランド申請が通ったあとに必ず引き直す**
- `itemcondition=Used` で中古の可否も同じ形で引ける
- 自社アカウントのセッションで自社の管理画面を見ているだけ。外部サイトの自動取得ではない

## 実績
2026-10-09：候補43件＋発注済1件＝**44 ASIN を判定。OK 39／NG 5**。
NG＝B08432J49S・B0CVX7YCKS・B0D9J6WR46・B0D9J7S94S・B0FVL8QST6（発注済の鍋）。
結果は `workspace/output/agent_output/T-20260920-003/buylist20261009/gate_check_20261009.csv`。
