/* popup: 監視登録・状態表示・購入待ちの操作 */
var $ = function (id) { return document.getElementById(id); };
function send(msg) { return new Promise(function (r) { chrome.runtime.sendMessage(msg, r); }); }
// D1: 未定義/非数値でも例外を出さない通貨表示
function yen(v) { return (typeof v === 'number' && isFinite(v)) ? '¥' + v.toLocaleString() : '—'; }
function itemIdFromUrl(url) {
  var m = url.match(/auction\/([a-zA-Z0-9]+)/) || url.match(/item\/([a-zA-Z0-9]+)/);
  return m ? m[1] : null;
}

function priceInput() {
  return {
    assumedWinningBid: +$('purchasePrice').value,
    procurementShipping: +$('procurementShipping').value,
    otherCost: +$('otherCost').value,
    targetMargin: +$('targetMargin').value
  };
}

$('previewBtn').onclick = function () {
  try {
    var p = self.RSAS.calcSellPrice(priceInput());
    $('calc').textContent = '販売価格 ¥' + p.sellPrice.toLocaleString() + ' / 損益分岐(上限仕入) ¥' + p.maxSourcePrice.toLocaleString() + ' / 想定利益 ¥' + p.estimatedProfit.toLocaleString();
  } catch (e) { $('calc').textContent = e.message; }
};

$('addBtn').onclick = async function () {
  var url = $('url').value.trim();
  var id = itemIdFromUrl(url);
  if (!$('asin').value || !$('sku').value || !id) { $('calc').textContent = 'ASIN/SKU/正しいヤフオクURL が必要です'; return; }
  var p = self.RSAS.calcSellPrice(priceInput());
  var state = await send({ type: 'GET_STATE' });
  var watches = state.watches || [];
  var watch = {
    id: 'w-' + $('sku').value,
    asin: $('asin').value.trim(), sku: $('sku').value.trim(),
    source: { platform: 'yahoo', itemId: id, url: url },
    purchasePrice: +$('purchasePrice').value, procurementShipping: +$('procurementShipping').value,
    otherCost: +$('otherCost').value, targetMargin: +$('targetMargin').value,
    sellPrice: p.sellPrice, maxSourcePrice: p.maxSourcePrice,
    quantity: 1, listingState: 'ACTIVE', status: 'UNKNOWN', currentPrice: null,
    checkFailCount: 0, active: true
  };
  var i = watches.findIndex(function (w) { return w.id === watch.id; });
  if (i >= 0) watches[i] = watch; else watches.push(watch);
  await new Promise(function (r) { chrome.storage.local.set({ watches: watches }, r); });
  $('calc').textContent = '登録しました。監視間隔ごとに自動チェックします。';
  render();
};

$('runBtn').onclick = async function () { $('runBtn').textContent = '実行中...'; await send({ type: 'RUN_MONITOR' }); $('runBtn').textContent = '今すぐ監視を1周'; render(); };
$('optLink').onclick = function (e) { e.preventDefault(); chrome.runtime.openOptionsPage(); };

async function render() {
  var s = await send({ type: 'GET_STATE' });
  $('dryBadge').style.display = (s.settings && s.settings.dryRun === false) ? 'none' : 'inline';

  var tasks = (s.tasks || []).filter(function (t) { return t.state === 'PENDING'; });
  $('tasks').innerHTML = tasks.length ? tasks.map(function (t) {
    return '<div class="item"><b>' + t.sku + '</b> <span class="pill PENDING">購入待ち</span><br>' +
      'Amazon注文 ' + t.amazonOrderId + ' / 上限 ' + yen(t.maxSourcePrice) + '<br>' +
      '<a href="' + t.sourceUrl + '" target="_blank">ヤフオクを開いて購入</a></div>';
  }).join('') : '<div class="note">なし</div>';

  var ws = s.watches || [];
  $('watches').innerHTML = ws.length ? ws.map(function (w) {
    var over = w.currentPrice != null && w.currentPrice > w.maxSourcePrice;
    return '<div class="item"><b>' + w.sku + '</b> <span class="pill ' + (w.status || 'UNKNOWN') + '">' + (w.status || '-') + '</span> ' +
      '在庫' + (w.quantity != null ? w.quantity : '-') + '<br>' + (w.asin || '') + '<br>' +
      '現在 <span class="' + (over ? 'over' : '') + '">' + (w.currentPrice != null ? yen(w.currentPrice) : '-') + '</span>' +
      ' / 上限 ' + yen(w.maxSourcePrice) + (w.active ? '' : ' <span class="pill INACTIVE">監視終了</span>') + '</div>';
  }).join('') : '<div class="note">未登録</div>';
}

render();
