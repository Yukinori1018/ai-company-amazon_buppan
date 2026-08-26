/* Satoy Select — 選び方ガイド（記事ページ）のふるまい
   方針:
   - アニメーションは「意味のあるもの」だけ。装飾のための動きは入れない
   - 画面外では止める（電池とCPUを無駄に使わない）
   - prefers-reduced-motion: reduce のときは自動再生しない。ただし利用者が自分で再生できる
   - JS が動かなくても、内容（表・文章）は全部読める                            */
(function () {
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---- 1. 読み進みバー ---- */
  var bar = document.querySelector('.progress i');
  if (bar) {
    var onScroll = function () {
      var h = document.documentElement.scrollHeight - window.innerHeight;
      bar.style.width = (h > 0 ? Math.min(100, (window.scrollY / h) * 100) : 0) + '%';
    };
    window.addEventListener('scroll', onScroll, {passive: true});
    window.addEventListener('resize', onScroll);
    onScroll();
  }

  /* ---- 2. 目次の現在地（スクロールスパイ） ---- */
  var links = [].slice.call(document.querySelectorAll('.toc a[href^="#"]'));
  if (links.length && 'IntersectionObserver' in window) {
    var map = {};
    links.forEach(function (a) {
      var t = document.getElementById(a.getAttribute('href').slice(1));
      if (t) map[t.id] = a;
    });
    var spy = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        links.forEach(function (a) { a.classList.remove('on'); });
        if (map[e.target.id]) map[e.target.id].classList.add('on');
      });
    }, {rootMargin: '-84px 0px -68% 0px'});
    Object.keys(map).forEach(function (id) { spy.observe(document.getElementById(id)); });
  }

  /* ---- 3. 実演アニメは画面内にあるときだけ動かす ---- */
  var stages = [].slice.call(document.querySelectorAll('[data-anim]'));
  var wanted = {};                                  // 利用者が明示的に止めたかどうか
  function apply(el, on) { el.classList.toggle('run', on); }

  if ('IntersectionObserver' in window) {
    var vis = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        var id = e.target.dataset.anim;
        var want = wanted[id];
        if (want === false) return;                 // 停止中なら触らない
        apply(e.target, e.isIntersecting && (want === true || !reduce));
      });
    }, {threshold: 0.25});
    stages.forEach(function (el) {
      wanted[el.dataset.anim] = reduce ? false : null;   // reduce なら既定は停止
      vis.observe(el);
    });
  } else {
    stages.forEach(function (el) { apply(el, !reduce); });
  }

  /* 再生／停止ボタン */
  [].slice.call(document.querySelectorAll('.playbtn')).forEach(function (btn) {
    var target = document.querySelector('[data-anim="' + btn.dataset.target + '"]');
    if (!target) return;
    var sync = function () {
      var on = target.classList.contains('run');
      btn.textContent = on ? '❙❙ 停止' : '▶ 再生';
      btn.setAttribute('aria-pressed', String(on));
    };
    btn.addEventListener('click', function () {
      var on = !target.classList.contains('run');
      wanted[btn.dataset.target] = on;
      apply(target, on);
      sync();
    });
    // 初期表示を合わせる（IntersectionObserver の適用後）
    setTimeout(sync, 60);
    target.addEventListener('transitionend', sync);
    window.addEventListener('scroll', function () { sync(); }, {passive: true});
  });

  /* ---- 4. 素材タブ（刃あたりの実演＋比較表の列ハイライトを連動） ---- */
  [].slice.call(document.querySelectorAll('.matswitch[data-controls]')).forEach(function (sw) {
    var demo = document.getElementById(sw.dataset.controls);
    var table = sw.dataset.table ? document.getElementById(sw.dataset.table) : null;
    var btns = [].slice.call(sw.querySelectorAll('button'));

    function select(m) {
      btns.forEach(function (b) { b.setAttribute('aria-selected', String(b.dataset.m === m)); });
      if (demo) demo.dataset.mat = m;
      if (table) {
        var i = btns.map(function (b) { return b.dataset.m; }).indexOf(m);
        [].slice.call(table.querySelectorAll('col')).forEach(function (c, ci) {
          c.classList.toggle('on', ci === i + 1);
        });
        [].slice.call(table.querySelectorAll('thead th')).forEach(function (th, ti) {
          th.classList.toggle('on', ti === i + 1);
        });
      }
      var scope = demo ? (demo.closest('.demo') || demo) : sw;
      var note = scope.querySelector('[data-note]');
      if (note && sw.dataset.notes) {
        try { note.innerHTML = JSON.parse(sw.dataset.notes)[m]; } catch (e) {}
      }
    }
    btns.forEach(function (b) {
      b.addEventListener('click', function () { select(b.dataset.m); });
      b.addEventListener('keydown', function (e) {
        var i = btns.indexOf(b), n = null;
        if (e.key === 'ArrowRight') n = btns[(i + 1) % btns.length];
        if (e.key === 'ArrowLeft') n = btns[(i - 1 + btns.length) % btns.length];
        if (n) { e.preventDefault(); n.focus(); select(n.dataset.m); }
      });
    });
    select(btns[0].dataset.m);
  });

  /* ---- 5. 中身×材質の相性マトリクス（ボトル記事） ---- */
  var pick = document.querySelector('.matrix-pick');
  var matrix = document.getElementById('matrix');
  if (pick && matrix) {
    var data = JSON.parse(matrix.dataset.map);
    var btns = [].slice.call(pick.querySelectorAll('button'));
    function show(key) {
      btns.forEach(function (b) { b.setAttribute('aria-selected', String(b.dataset.k === key)); });
      [].slice.call(matrix.querySelectorAll('.cell')).forEach(function (cell) {
        var row = data[key][cell.dataset.mat];
        cell.dataset.v = row.v;
        cell.querySelector('.mark').textContent = row.v === 'ok' ? '○' : (row.v === 'no' ? '✕' : '—');
        cell.querySelector('.desc').textContent = row.t;
      });
      var lead = document.getElementById('matrix-lead');
      if (lead) lead.textContent = data[key]._lead;
    }
    btns.forEach(function (b) { b.addEventListener('click', function () { show(b.dataset.k); }); });
    show(btns[0].dataset.k);
  }
})();
