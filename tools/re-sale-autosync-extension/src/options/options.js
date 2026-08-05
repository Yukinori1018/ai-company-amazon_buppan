var DEFAULTS = {
  dryRun: true, referralRate: 0.15, monitorIntervalMin: 20,
  dailySpendCapJPY: 20000, spentTodayJPY: 0, spentDate: '',
  sellerCentralInventoryUrl: 'https://sellercentral.amazon.co.jp/inventory'
};
var $ = function (id) { return document.getElementById(id); };

chrome.storage.local.get('settings', function (r) {
  var s = Object.assign({}, DEFAULTS, r.settings || {});
  $('dryRun').checked = s.dryRun !== false;
  $('monitorIntervalMin').value = s.monitorIntervalMin;
  $('dailySpendCapJPY').value = s.dailySpendCapJPY;
  $('referralRate').value = s.referralRate;
  $('sellerCentralInventoryUrl').value = s.sellerCentralInventoryUrl;
});

$('save').onclick = function () {
  chrome.storage.local.get('settings', function (r) {
    var s = Object.assign({}, DEFAULTS, r.settings || {}, {
      dryRun: $('dryRun').checked,
      monitorIntervalMin: Math.max(1, +$('monitorIntervalMin').value || 20),
      dailySpendCapJPY: +$('dailySpendCapJPY').value || 0,
      referralRate: +$('referralRate').value || 0.15,
      sellerCentralInventoryUrl: $('sellerCentralInventoryUrl').value.trim()
    });
    chrome.storage.local.set({ settings: s }, function () {
      chrome.runtime.sendMessage({ type: 'RESCHEDULE' });
      $('saved').textContent = '保存しました';
      setTimeout(function () { $('saved').textContent = ''; }, 1500);
    });
  });
};
