/**
 * 依存ゼロのユニットテストランナー（Node）。
 *   実行: node test/run.js
 * 拡張の lib は IIFE で `self.RSAS` に生やすため、global.self を用意してから読み込む。
 * chrome.* はテスト用のスタブを差し込む（store.js の canSpend/addSpend を実挙動で検証するため）。
 */
'use strict';
const fs = require('fs');
const path = require('path');

// ---- 環境スタブ ----
global.self = {};
// chrome.storage.local を最小実装でスタブ（settings/watches/tasks/logs を1オブジェクトで保持）
const _mem = {};
global.chrome = {
  storage: { local: {
    get(keys, cb) {
      const out = {};
      const list = Array.isArray(keys) ? keys : [keys];
      list.forEach(k => { if (_mem[k] !== undefined) out[k] = _mem[k]; });
      cb(out);
    },
    set(obj, cb) { Object.assign(_mem, obj); if (cb) cb(); }
  } }
};

// ---- 対象読み込み ----
function load(rel) { require(path.join(__dirname, '..', 'src', rel)); }
load('lib/pricing.js');
load('lib/decide.js');
load('lib/store.js');
const RSAS = global.self.RSAS;

// ---- 極小アサート ----
let pass = 0, fail = 0;
const fails = [];
function eq(actual, expected, msg) {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a === e) { pass++; } else { fail++; fails.push(`${msg}\n    expected ${e}\n    actual   ${a}`); }
}
function ok(cond, msg) { if (cond) pass++; else { fail++; fails.push(msg); } }
function throws(fn, msg) { try { fn(); fail++; fails.push(msg + ' (throwを期待)'); } catch (_) { pass++; } }
function fx(name) { return fs.readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'); }

// ========== pricing ==========
(function () {
  const r = RSAS.calcSellPrice({ assumedWinningBid: 3000, procurementShipping: 500, otherCost: 0, targetMargin: 0.2, referralRate: 0.15, roundTo: 10 });
  eq(r.sellPrice, 5390, 'pricing: sellPrice');
  eq(r.maxSourcePrice, 4081, 'pricing: maxSourcePrice(損益分岐)');
  eq(r.estimatedProfit, 1081, 'pricing: estimatedProfit');
  ok(Math.abs(r.estimatedMargin - 0.2) < 0.01, 'pricing: margin≈目標');
  // 買値=損益分岐なら利益ゼロ近傍（安全側=それ以下でしか買わない設計）
  ok(r.maxSourcePrice < r.sellPrice, 'pricing: 上限<販売価格');
  throws(() => RSAS.calcSellPrice({ assumedWinningBid: 1000, targetMargin: 0.9, referralRate: 0.15 }), 'pricing: 利益率過大でthrow');
})();

// ========== decide ==========
(function () {
  eq(RSAS.decide('ENDED', 1000, 4081), { quantity: 0, reason: 'AUCTION_ENDED' }, 'decide: ENDED→0');
  eq(RSAS.decide('CANCELLED', 1000, 4081), { quantity: 0, reason: 'AUCTION_CANCELLED' }, 'decide: CANCELLED→0');
  eq(RSAS.decide('NOT_FOUND', null, 4081), { quantity: 0, reason: 'AUCTION_NOT_FOUND' }, 'decide: NOT_FOUND→0');
  eq(RSAS.decide('ACTIVE', 4000, 4081), { quantity: 1, reason: 'PROCURABLE' }, 'decide: ACTIVE価格内→1');
  const over = RSAS.decide('ACTIVE', 5000, 4081);
  eq(over.quantity, 0, 'decide: ACTIVE上限超→0');
  ok(/^PRICE_OVER_MAX/.test(over.reason), 'decide: 上限超の理由');
  eq(RSAS.decide('ACTIVE', null, 4081), { quantity: 1, reason: 'PROCURABLE_PRICE_UNKNOWN' }, 'decide: ACTIVE価格不明→1(理由分離)');
  eq(RSAS.decide('UNKNOWN', null, 4081), { quantity: null, reason: 'UNKNOWN_SKIP' }, 'decide: UNKNOWN→null');
})();

// ========== parseYahooHtml ==========
(function () {
  const a = RSAS.parseYahooHtml(fx('active_auction.html'));
  eq(a.status, 'ACTIVE', 'parse: 開催中→ACTIVE');
  eq(a.currentPrice, 4000, 'parse: 現在価格抽出');
  const e = RSAS.parseYahooHtml(fx('ended_auction.html'));
  eq(e.status, 'ENDED', 'parse: 終了→ENDED（おすすめのカート文言に釣られない）');
  eq(RSAS.parseYahooHtml(fx('not_found.html')).status, 'NOT_FOUND', 'parse: 404文言→NOT_FOUND');
  eq(RSAS.parseYahooHtml(fx('cancelled.html')).status, 'CANCELLED', 'parse: 削除→CANCELLED');
  const f = RSAS.parseYahooHtml(fx('flea_active.html'));
  eq(f.status, 'ACTIVE', 'parse: フリマ購入手続き→ACTIVE');
  eq(f.currentPrice, 3500, 'parse: フリマ販売価格抽出');
  eq(RSAS.parseYahooHtml('').status, 'UNKNOWN', 'parse: 空→UNKNOWN');
  eq(RSAS.parseYahooHtml('<html><body>意味不明</body></html>').status, 'UNKNOWN', 'parse: シグナル無→UNKNOWN');
})();

// ========== store: 日次購入上限 canSpend/addSpend ==========
(async function () {
  const today = '2026-08-12';
  // 初期: 上限20000。19000使用済みにする
  await RSAS.Store.saveSettings({ dailySpendCapJPY: 20000, spentTodayJPY: 0, spentDate: today });
  ok(await RSAS.Store.canSpend(5000, today) === true, 'store: 枠内はcanSpend=true');
  await RSAS.Store.addSpend(19000, today);
  ok(await RSAS.Store.canSpend(5000, today) === false, 'store: 累計超過はcanSpend=false');
  ok(await RSAS.Store.canSpend(1000, today) === true, 'store: 残枠内はtrue(19000+1000=20000)');
  // 日跨ぎでリセット
  ok(await RSAS.Store.canSpend(5000, '2026-08-13') === true, 'store: 翌日は枠リセットでtrue');

  // ---- 結果表示 ----
  console.log(`\n  PASS ${pass} / FAIL ${fail}`);
  if (fail) { console.log('\n  --- 失敗 ---\n  ' + fails.join('\n  ')); process.exit(1); }
  else { console.log('  ✅ 全テスト通過\n'); process.exit(0); }
})();
