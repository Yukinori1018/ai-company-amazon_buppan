var DEFAULT_SELECTORS = {
  amazonOrderRow: '[data-test-id="order-card"], .order-card, tr.order-row',
  amazonSku: '[data-test-id="sku"], .sku',
  amazonInventoryRow: '[data-test-id="inventory-row"], tr',
  amazonQtyInput: 'input[name*="quantity"], input[type="number"]',
  amazonSaveBtn: 'button[type="submit"], .save-button',
  yahooBuyLabels: ['購入手続きへ', '今すぐ落札', '即決で落札', '購入する', 'カートに入れる']
};
var DEFAULTS = {
  dryRun: true, referralRate: 0.15, monitorIntervalMin: 20,
  dailySpendCapJPY: 20000, spentTodayJPY: 0, spentDate: '',
  sellerCentralInventoryUrl: 'https://sellercentral.amazon.co.jp/inventory',
  selectors: DEFAULT_SELECTORS
};
var $ = function (id) { return document.getElementById(id); };
var SEL_KEYS = ['amazonOrderRow', 'amazonSku', 'amazonInventoryRow', 'amazonQtyInput', 'amazonSaveBtn'];

chrome.storage.local.get('settings', function (r) {
  var s = Object.assign({}, DEFAULTS, r.settings || {});
  var sel = Object.assign({}, DEFAULT_SELECTORS, (r.settings && r.settings.selectors) || {});
  $('dryRun').checked = s.dryRun !== false;
  $('monitorIntervalMin').value = s.monitorIntervalMin;
  $('dailySpendCapJPY').value = s.dailySpendCapJPY;
  $('referralRate').value = s.referralRate;
  $('sellerCentralInventoryUrl').value = s.sellerCentralInventoryUrl;
  SEL_KEYS.forEach(function (k) { $('sel_' + k).value = sel[k] || ''; });
  $('sel_yahooBuyLabels').value = (sel.yahooBuyLabels || []).join(', ');
});

$('save').onclick = function () {
  chrome.storage.local.get('settings', function (r) {
    // セレクタ: 空欄は既定へフォールバック
    var selectors = {};
    SEL_KEYS.forEach(function (k) {
      var v = $('sel_' + k).value.trim();
      selectors[k] = v || DEFAULT_SELECTORS[k];
    });
    var labels = $('sel_yahooBuyLabels').value.split(',').map(function (x) { return x.trim(); }).filter(Boolean);
    selectors.yahooBuyLabels = labels.length ? labels : DEFAULT_SELECTORS.yahooBuyLabels;

    var s = Object.assign({}, DEFAULTS, r.settings || {}, {
      dryRun: $('dryRun').checked,
      monitorIntervalMin: Math.max(1, +$('monitorIntervalMin').value || 20),
      dailySpendCapJPY: +$('dailySpendCapJPY').value || 0,
      referralRate: +$('referralRate').value || 0.15,
      sellerCentralInventoryUrl: $('sellerCentralInventoryUrl').value.trim(),
      selectors: selectors
    });
    chrome.storage.local.set({ settings: s }, function () {
      chrome.runtime.sendMessage({ type: 'RESCHEDULE' });
      $('saved').textContent = '保存しました';
      setTimeout(function () { $('saved').textContent = ''; }, 1500);
    });
  });
};
