/* SD 企業別 商品一覧を「同一オリジン iframe」で読み、卸価格つきで返す。
 *
 * 前提
 *   - 実行するのは秘書カズヨ（Chrome・SD にログイン済み・www.superdelivery.com のタブ）。
 *   - CDP の 1回の JS 実行は 45 秒で切られるため、**自分で 33 秒で打ち切って返す**。
 *   - 進捗は localStorage（キー `sdx_v1`）。同じ run() をもう一度呼べば続きから進む。
 *   - 一覧ページは 120件/ページ。**JAN は一覧に無い**（商品ページか JAN 検索で取る）。
 *
 * 使い方（3手）
 *   1) このファイル全文を Runtime.evaluate で流す（window.SDX が入る）
 *   2) SDX.seed([['102452','丸進'],['21321','和平フレイズ'], ...])   // 優先順に並べた配列
 *   3) await SDX.run()  を「done:true」が返るまで繰り返す。返り値 rows を毎回シートに追記する
 *
 * 返り値
 *   { done, cursor:{i,pg}, scanned:{dealers,pages}, rows:[ {...} ], note }
 *   rows[] = { dealer_id, dealer_name, page, product_code, name, price_text, raw }
 *   price_text は「円」を含む行を拾ったもの、raw はブロック全文（初回に目で見てマッピングを確定するため）。
 *
 * 注意（CLAUDE.md）
 *   - 卸価格は会員限定の取引条件。**PUBLIC リポには書かない。**シートと agent_output/ だけ。
 *   - このスクリプトは読み取り専用。カートに入れる・申請する・注文する操作は一切しない。
 */
(function () {
  'use strict';
  var KEY = 'sdx_v1';
  var BUDGET_MS = 33000;      // CDP の 45 秒制限に対する安全マージン
  var PER_PAGE = 120;
  var WAIT_MS = 12000;        // 1ページの描画待ちの上限
  var GAP_MS = 350;           // ページ間の間隔（SD は 429 を返すことがある）

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || null; } catch (e) { return null; }
  }
  function save(s) { localStorage.setItem(KEY, JSON.stringify(s)); }

  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  /* 同一オリジンの iframe にページを読み込み、商品ブロックが現れるまで待って document を返す */
  function loadPage(url) {
    return new Promise(function (resolve, reject) {
      var f = document.createElement('iframe');
      f.style.cssText = 'position:fixed;left:-9999px;top:0;width:1200px;height:900px;';
      var settled = false;
      var t0 = Date.now();
      function finish(doc, err) {
        if (settled) return;
        settled = true;
        try { f.remove(); } catch (e) {}
        if (err) reject(err); else resolve(doc);
      }
      f.onload = function () {
        var poll = setInterval(function () {
          var doc;
          try { doc = f.contentDocument; } catch (e) { clearInterval(poll); finish(null, new Error('cross-origin')); return; }
          if (!doc) return;
          var hit = doc.querySelector('.itembox-parts, li.card, .item-name, .trading-condition, table');
          var blocked = /Just a moment|Too Many Requests|429/i.test(doc.title || '');
          if (blocked) { clearInterval(poll); finish(null, new Error('blocked:' + doc.title)); return; }
          if (hit) { clearInterval(poll); finish(doc, null); return; }
          if (Date.now() - t0 > WAIT_MS) { clearInterval(poll); finish(doc, null); return; }  // 空ページも返す
        }, 200);
      };
      f.onerror = function () { finish(null, new Error('iframe error')); };
      f.src = url;
      document.body.appendChild(f);
    });
  }

  function totalOf(doc) {
    var el = doc.querySelector('.page-nav-numtxt');
    if (!el) return null;
    var m = (el.textContent || '').replace(/,/g, '').match(/全(\d+)件/);
    return m ? parseInt(m[1], 10) : null;
  }

  /* 商品ブロックを拾う。DOM が変わっても壊れないよう、商品リンクを起点に親へ遡る */
  function itemsOf(doc) {
    var out = [], seen = {};
    var anchors = doc.querySelectorAll('a[href*="/p/r/pd_p/"]');
    for (var i = 0; i < anchors.length; i++) {
      var a = anchors[i];
      var m = (a.getAttribute('href') || '').match(/\/p\/r\/pd_p\/(\d+)\//);
      if (!m) continue;
      var code = m[1];
      if (seen[code]) continue;
      var block = a.closest('.itembox-parts') || a.closest('li') || a.parentElement;
      if (!block) continue;
      seen[code] = 1;
      var nameEl = block.querySelector('.item-name a') || a;
      var name = (nameEl.textContent || a.getAttribute('title') || '').replace(/\s+/g, ' ').trim();
      if (!name) {
        var img = block.querySelector('img[title], img[alt]');
        if (img) name = (img.getAttribute('title') || img.getAttribute('alt') || '').trim();
      }
      var raw = (block.innerText || block.textContent || '').replace(/\s*\n\s*/g, ' / ').replace(/\s+/g, ' ').trim();
      var priceLines = raw.split(' / ').filter(function (s) { return /円|セット|掛/.test(s); });
      out.push({
        product_code: code,
        name: name,
        price_text: priceLines.join(' | '),
        raw: raw.slice(0, 400)
      });
    }
    return out;
  }

  var SDX = {
    /** dealers: [[dealer_id, name], ...] を優先順に渡す。既存の進捗は捨てて作り直す */
    seed: function (dealers) {
      var s = { dealers: dealers, i: 0, pg: 1, total: null, emitted: 0, startedAt: new Date().toISOString() };
      save(s);
      return { seeded: dealers.length };
    },
    /** 進捗を見る */
    status: function () {
      var s = load();
      if (!s) return { seeded: false };
      return { seeded: true, i: s.i, of: s.dealers.length, pg: s.pg, emitted: s.emitted,
               current: s.dealers[s.i] || null };
    },
    /** 進捗を捨てる */
    reset: function () { localStorage.removeItem(KEY); return { reset: true }; },

    /** 予算内で回して、今回ぶんの行を返す。done:false が返る限り呼び直す */
    run: async function (budgetMs) {
      var s = load();
      if (!s) return { error: 'seed していません。SDX.seed([[dealer_id,name],...]) を先に呼んでください' };
      var budget = budgetMs || BUDGET_MS;
      var t0 = Date.now();
      var rows = [], pages = 0, dealers = 0, note = [];

      while (s.i < s.dealers.length) {
        if (Date.now() - t0 > budget) break;
        var d = s.dealers[s.i];
        var did = String(d[0]), dname = d[1] || '';
        var url = s.pg === 1
          ? 'https://www.superdelivery.com/p/do/dpsl/' + did + '/'
          : 'https://www.superdelivery.com/p/do/dpsl/' + did + '/all/' + s.pg + '/';
        var doc;
        try {
          doc = await loadPage(url);
        } catch (e) {
          note.push(did + ' pg' + s.pg + ': ' + e.message);
          if (/blocked/.test(e.message)) { save(s); break; }   // 止められたら安全に抜ける
          s.i += 1; s.pg = 1; s.total = null; save(s); continue;
        }
        if (s.pg === 1) s.total = totalOf(doc);
        var items = itemsOf(doc);
        pages += 1;
        for (var k = 0; k < items.length; k++) {
          items[k].dealer_id = did;
          items[k].dealer_name = dname;
          items[k].page = s.pg;
          rows.push(items[k]);
        }
        s.emitted += items.length;
        var lastPage = (s.total === null) ? (items.length < PER_PAGE)
                                          : (s.pg >= Math.ceil(s.total / PER_PAGE));
        if (items.length === 0 || lastPage) { s.i += 1; dealers += 1; s.pg = 1; s.total = null; }
        else { s.pg += 1; }
        save(s);
        await sleep(GAP_MS);
      }
      return {
        done: s.i >= s.dealers.length,
        cursor: { i: s.i, of: s.dealers.length, pg: s.pg },
        scanned: { dealers: dealers, pages: pages },
        rows: rows,
        note: note.join(' ; ')
      };
    }
  };

  /* ------------------------------------------------------------------
   * 取引条件スキャン（SDX.terms）
   *   /p/do/dpsl/dcc/<dealer_id>/ を読み、Amazon で売ってよい社を切り出す。
   *   ページは非ログインでも 200 だが、**HTTP で連続取得すると SD が 429 を返し続ける**
   *   （2026-09-30 実測。8/16/32/64秒のバックオフでも復帰せず）。
   *   一方、ログイン済みブラウザの iframe は 1ページ約1秒で回った（カズヨ実測・44ページ）。
   *   → **このスキャンはブラウザ側で回すのが正解。**
   *
   *   使い方: SDX.termsSeed([[id,name],...]) → await SDX.terms() を done まで繰り返す
   *   返り値 rows[] = { dealer_id, dealer_name, ネット販売, 消費者への直送, 仕入れ前の販売,
   *                     画像転載, 代金引換, amazon_context, judge }
   *   🔴 dcc ページには**送料表の実額**が載る。rows に送料は入れていない（PUBLIC リポ対策）。
   * ------------------------------------------------------------------ */
  var TKEY = 'sdx_terms_v1';
  var LABELS = ['ネット販売', '消費者への直送', '仕入れ前の販売', '画像転載', '代金引換'];

  function markOf(td) {
    if (!td) return '記載なし';
    var h = td.innerHTML || '';
    var t = (td.textContent || '').trim();
    if (/fa-xmark|fa-times/.test(h) || t.indexOf('×') >= 0) return '×';
    if (/triangle/.test(h) || t.indexOf('△') >= 0) return '△';
    if (/fa-circle/.test(h) || t.indexOf('○') >= 0) return '○';
    return t ? t.slice(0, 12) : '記載なし';
  }

  function termsOf(doc) {
    var out = {};
    for (var i = 0; i < LABELS.length; i++) {
      var td = null;
      var cells = doc.querySelectorAll('th, td');
      for (var j = 0; j < cells.length; j++) {
        if ((cells[j].textContent || '').trim() === LABELS[i]) {
          td = cells[j].nextElementSibling; break;
        }
      }
      out[LABELS[i]] = markOf(td);
    }
    var flat = (doc.body ? (doc.body.innerText || doc.body.textContent || '') : '').replace(/\s+/g, ' ');
    var ctx = [];
    var re = /.{0,70}(?:Amazon|amazon|アマゾン).{0,90}/g, m;
    while ((m = re.exec(flat)) !== null && ctx.length < 4) ctx.push(m[0]);
    out.amazon_context = ctx.join(' || ');
    var namedNg = /(遠慮|不可|禁止|お断り|NG)/.test(out.amazon_context);
    out.judge = (out['ネット販売'] === '×' || namedNg) ? '×'
              : (out['ネット販売'] === '△') ? '要確認'
              : (out['ネット販売'] === '○') ? '○' : '不明';
    return out;
  }

  SDX.termsSeed = function (dealers) {
    save2({ dealers: dealers, i: 0, startedAt: new Date().toISOString() });
    return { seeded: dealers.length };
  };
  function load2() { try { return JSON.parse(localStorage.getItem(TKEY)) || null; } catch (e) { return null; } }
  function save2(s) { localStorage.setItem(TKEY, JSON.stringify(s)); }
  SDX.termsStatus = function () { var s = load2(); return s ? { i: s.i, of: s.dealers.length } : { seeded: false }; };
  SDX.termsReset = function () { localStorage.removeItem(TKEY); return { reset: true }; };
  SDX.terms = async function (budgetMs) {
    var s = load2();
    if (!s) return { error: 'SDX.termsSeed([[id,name],...]) を先に呼んでください' };
    var budget = budgetMs || BUDGET_MS, t0 = Date.now(), rows = [], note = [];
    while (s.i < s.dealers.length) {
      if (Date.now() - t0 > budget) break;
      var d = s.dealers[s.i], did = String(d[0]), dname = d[1] || '';
      var doc;
      try {
        doc = await loadPage('https://www.superdelivery.com/p/do/dpsl/dcc/' + did + '/');
      } catch (e) {
        note.push(did + ': ' + e.message);
        if (/blocked/.test(e.message)) { save2(s); break; }
        s.i += 1; save2(s); continue;
      }
      var t = termsOf(doc);
      t.dealer_id = did; t.dealer_name = dname;
      rows.push(t);
      s.i += 1; save2(s);
      await sleep(GAP_MS);
    }
    return { done: s.i >= s.dealers.length, cursor: { i: s.i, of: s.dealers.length },
             rows: rows, note: note.join(' ; ') };
  };

  window.SDX = SDX;
  return { installed: true,
           api: ['SDX.seed(dealers)', 'SDX.run(budgetMs)', 'SDX.status()', 'SDX.reset()',
                 'SDX.termsSeed(dealers)', 'SDX.terms(budgetMs)', 'SDX.termsStatus()', 'SDX.termsReset()'] };
})();
