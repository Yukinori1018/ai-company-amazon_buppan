/* Satoy Select — デザイン案 v1 のふるまい
   方針: 動きは「画面に入ったら一度だけフェードイン」だけに絞る。
         スクロール追従・パララックス・ピン留めは入れない。
   prefers-reduced-motion: reduce のときはフェードインを行わない
   （要素は最初から表示。UI の開閉は動作する）。 */
(function () {
  var root = document.documentElement;
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---- 1. モバイル: メニューの開閉（動きの設定に関わらず必要） ---- */
  var toggle = document.getElementById('navToggle');
  var nav = document.getElementById('siteNav');
  if (toggle && nav) {
    var setOpen = function (open) {
      nav.classList.toggle('open', open);
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? 'メニューを閉じる' : 'メニューを開く');
    };
    toggle.addEventListener('click', function () {
      setOpen(!nav.classList.contains('open'));
    });
    nav.addEventListener('click', function (e) {
      if (e.target.closest('a')) setOpen(false);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && nav.classList.contains('open')) {
        setOpen(false);
        toggle.focus();
      }
    });
  }

  /* ---- 2. ヘッダー: 少しスクロールしたら境界線を出す ---- */
  var header = document.getElementById('siteHeader');
  if (header) {
    var onScroll = function () { header.classList.toggle('stuck', window.scrollY > 8); };
    window.addEventListener('scroll', onScroll, {passive: true});
    onScroll();
  }

  /* ---- 3. フェードイン ---- */
  if (reduce || !('IntersectionObserver' in window)) return;
  root.classList.add('js');

  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      var d = parseFloat(e.target.dataset.d || 0) * 70;
      e.target.style.transitionDelay = d + 'ms';
      e.target.classList.add('in');
      io.unobserve(e.target);
    });
  }, {rootMargin: '0px 0px -12% 0px', threshold: 0.08});

  document.querySelectorAll('.reveal').forEach(function (el) { io.observe(el); });
})();
