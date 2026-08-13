/**
 * Background service worker（MV3・classic）。
 * importScripts で共通ロジックを読み込み、以下を統括する:
 *   1) 監視サイクル(alarm): 各 watch のヤフオクを fetch→判定→在庫希望値を更新し、要変更を通知
 *   2) Amazon 注文の受信(content script から): 購入タスク作成＋通知（半自動購入のトリガ）
 *   3) popup / content script とのメッセージ橋渡し
 *
 * ※ 拡張のみ構成のため常駐サーバー無し。監視は Chrome 起動中のみ動作する。
 * ※ Amazon 在庫0化・注文検知はセラーセントラルのログイン済みセッション経由（SP-API秘密鍵は保存しない）。
 */
importScripts('lib/pricing.js', 'lib/decide.js', 'lib/store.js');
var Store = self.RSAS.Store;

function todayStr() {
  var d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function notify(id, title, message) {
  chrome.notifications.create(id, {
    type: 'basic', iconUrl: chrome.runtime.getURL('icons/icon128.png'),
    title: title, message: message, priority: 2
  });
}

// ---- 初期化 ----
chrome.runtime.onInstalled.addListener(async function () {
  var s = await Store.getSettings();
  await Store.saveSettings(s); // デフォルトを確定
  await rescheduleAlarm();
});
chrome.runtime.onStartup.addListener(rescheduleAlarm);

async function rescheduleAlarm() {
  var s = await Store.getSettings();
  chrome.alarms.create('monitor', { periodInMinutes: Math.max(1, s.monitorIntervalMin) });
}

chrome.alarms.onAlarm.addListener(function (a) {
  if (a.name === 'monitor') runMonitorCycle();
});

// ---- 1) 監視サイクル: ヤフオク状態→在庫希望値 ----
async function runMonitorCycle() {
  var watches = await Store.getWatches();
  var active = watches.filter(function (w) { return w.active; });
  for (var i = 0; i < active.length; i++) {
    await syncOne(active[i]).catch(function (e) {
      console.warn('syncOne failed', e);
    });
    await sleep(1500 + Math.floor(Math.random() * 1500)); // ポライトネス（ジッタ）
  }
}

function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

async function syncOne(watch) {
  var snap = await fetchYahooSnapshot(watch.source.url);
  var d = self.RSAS.decide(snap.status, snap.currentPrice, watch.maxSourcePrice);

  await Store.updateWatch(watch.id, {
    status: snap.status,
    currentPrice: snap.currentPrice,
    lastCheckedAt: new Date().toISOString(),
    checkFailCount: snap.status === 'UNKNOWN' ? (watch.checkFailCount || 0) + 1 : 0
  });

  if (d.quantity === null) return;            // UNKNOWN: 触らない
  if (d.quantity === watch.quantity) return;  // 冪等

  // 在庫を変える必要がある → Amazon 側の在庫更新を要求（セラーセントラル自動化 or 手動）
  await requestAmazonStockChange(watch, d.quantity, d.reason);
}

// ヤフオクのスナップショット取得（fetch + 正規表現）
async function fetchYahooSnapshot(url) {
  try {
    var res = await fetch(url, { credentials: 'omit' });
    if (res.status === 404) return { status: 'NOT_FOUND', currentPrice: null };
    if (res.status === 429 || res.status === 503) return { status: 'UNKNOWN', currentPrice: null };
    var html = await res.text();
    return self.RSAS.parseYahooHtml(html);
  } catch (e) {
    return { status: 'UNKNOWN', currentPrice: null };
  }
}

// Amazon 在庫変更の指示（拡張のみ: セラーセントラルの content script に依頼。DRY_RUN 時は通知のみ）
async function requestAmazonStockChange(watch, quantity, reason) {
  var s = await Store.getSettings();
  await Store.updateWatch(watch.id, { quantity: quantity, listingState: quantity === 0 ? 'INACTIVE' : 'ACTIVE' });
  await Store.log({ kind: 'STOCK', sku: watch.sku, action: quantity === 0 ? 'SET_OUT_OF_STOCK' : 'SET_IN_STOCK', reason: reason, dryRun: s.dryRun });

  if (quantity === 0) {
    notify('stock0-' + watch.sku, '在庫0にすべき仕入れ元が消滅/超過', watch.sku + '（' + reason + '）。Amazon在庫を0にします。');
  }
  // 消滅系は監視終了（価格超過は復帰し得るので継続）
  if (reason.indexOf('AUCTION_') === 0) {
    await Store.updateWatch(watch.id, { active: false });
  }

  // セラーセントラルのタブがあれば在庫変更を依頼（best-effort）
  chrome.tabs.query({ url: '*://sellercentral.amazon.co.jp/*' }, function (tabs) {
    if (!tabs || !tabs.length) return;
    chrome.tabs.sendMessage(tabs[0].id, { type: 'SET_STOCK', sku: watch.sku, quantity: quantity, dryRun: s.dryRun });
  });
}

// ---- 2) Amazon 注文の受信（amazon_seller.js が注文一覧から拾って送る）----
async function onAmazonOrders(orders) {
  var watches = await Store.getWatches();
  for (var i = 0; i < orders.length; i++) {
    var o = orders[i];
    var w = watches.find(function (x) { return x.sku === o.sku; });
    if (!w) continue; // 監視対象外
    var task = await Store.addTask({
      id: 'task-' + o.amazonOrderId + '-' + o.sku,
      watchId: w.id, sku: o.sku, asin: w.asin,
      amazonOrderId: o.amazonOrderId,
      sourceUrl: w.source.url, maxSourcePrice: w.maxSourcePrice,
      qty: o.qty || 1, state: 'PENDING', createdAt: new Date().toISOString()
    });
    if (task.state === 'PENDING') {
      notify('buy-' + task.id, 'Amazon注文→ヤフオク購入が必要', w.sku + ' の注文。拡張から1クリックで購入を確定してください。');
      await Store.log({ kind: 'ORDER', sku: o.sku, amazonOrderId: o.amazonOrderId, action: 'PURCHASE_TASK_CREATED' });
    }
  }
}

// ---- 3) メッセージ橋渡し ----
chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
  (async function () {
    switch (msg.type) {
      case 'RUN_MONITOR': await runMonitorCycle(); sendResponse({ ok: true }); break;
      case 'AMAZON_ORDERS': await onAmazonOrders(msg.orders || []); sendResponse({ ok: true }); break;
      case 'PURCHASE_RESULT': await onPurchaseResult(msg); sendResponse({ ok: true }); break;
      case 'RESCHEDULE': await rescheduleAlarm(); sendResponse({ ok: true }); break;
      case 'GET_STATE': {
        sendResponse({
          watches: await Store.getWatches(), tasks: await Store.getTasks(),
          settings: await Store.getSettings(), logs: (await Store.getLogs()).slice(0, 50)
        });
        break;
      }
      default: sendResponse({ ok: false, error: 'unknown message' });
    }
  })();
  return true; // async
});

// 購入結果（yahoo.js の購入確定 or 失敗）
async function onPurchaseResult(msg) {
  var task = (await Store.getTasks()).find(function (t) { return t.id === msg.taskId; });
  if (!task) return;
  if (msg.success) {
    await Store.updateTask(task.id, { state: 'BOUGHT', boughtPrice: msg.price, boughtAt: new Date().toISOString() });
    await Store.addSpend(msg.price || 0, todayStr());
    // 買えたのでこの一点物は消える → 該当 SKU の在庫は0へ
    var w = (await Store.getWatches()).find(function (x) { return x.id === task.watchId; });
    if (w) await requestAmazonStockChange(w, 0, 'PURCHASED_ON_YAHOO');
    await Store.log({ kind: 'PURCHASE', sku: task.sku, action: 'BOUGHT', price: msg.price });
  } else {
    await Store.updateTask(task.id, { state: 'FAILED', error: msg.error });
    notify('buyfail-' + task.id, 'ヤフオク購入に失敗', task.sku + '：' + (msg.error || '') + ' → Amazon注文のキャンセルを検討してください。');
    await Store.log({ kind: 'PURCHASE', sku: task.sku, action: 'FAILED', error: msg.error });
  }
}
