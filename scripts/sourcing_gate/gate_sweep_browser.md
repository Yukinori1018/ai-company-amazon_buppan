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

## 申請画面まで読む（2026-10-20 追加・CLAUDE.md §F8）

社長指示「仕入れリストに入れた時点で出品申請をしてほしい」。上の判定（OK/NG）だけでは、
**書類が要るのか・何点要るのか**が分からない（台帳の「可（新品）」は「申請経路がある」だけ）。
「出品許可を申請する」を押して、開いた申請画面の文言を読む。押すと Amazon 側に申請の下書きができるだけで、送信はしない。

### 区分
| 画面 | 区分 |
|---|---|
| `この商品は以下のコンディションで販売できます：新品`／新品に許可が要らない | 申請不要（新品で出品可） |
| 申請画面に `合計N点以上` `合計購入数がNユニット以上` | 要書類（N点以上）。**N は10とは限らない**（Panasonic 30／LION 100） |
| 「受け付けていません」に `その他の商品` | 不可（新品の申請経路なし）。押さない |
| 押すと `サポートされていないアクション` | 要確認（別 ASIN の申請に飛ばされる。B001CNHI8G） |

### 手順（`javascript_tool`・セラセンのページを開いたタブで）
- 申請ボタンは `span` で、**見えている（`getBoundingClientRect().width>0`）ものを `click()`** する（同じ文言の要素が4つあり、隠れたものを押すと別 ASIN に飛ぶ）
- 押したあとの画面は SPA で描画が遅い。**元の画面の文言（`出品許可を申請する`）が消え、`必要書類|出品資格|サポートされていない` が出るまで待つ**
- 結果は **1件ごとに `localStorage` に保存**する。10/20 に結果をメモリだけに持って回し、タブが固まって約90件を失った。localStorage なら同じオリジンの新しいタブから読み出せる
- iframe の同時実行は3つまで（4〜5で遅くなり、2回固まった）。3並列で約20件/分
- 出力は `[?&=]` を含むとツールに遮られる（申請画面の URL に applicationId が入るため）。URL は返さない
- 台帳への書き込み：`agent_output/T-20260920-003/apply_probe_20261020/write_ledger.py results.tsv`（ASIN・区分・種別の TSV。判定列は触らない）

### 実績
2026-10-20：台帳の GO・UNKNOWN 304件。申請不要58／要書類10点233・30点3・100点1／不可8／要確認1。
「可（新品）」だった GO 4件は、要書類10点が2・30点が1・要確認が1で、**すぐ出品できるものは0件**だった。
