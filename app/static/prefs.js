// Privacy mode (Settings → Appearance, this device): amounts are blurred until tapped. The first
// tap on a blurred amount reveals it (and doesn't follow a link it sits in); it stays visible
// until you leave the page.
(function () {
  var root = document.documentElement;
  var AMOUNTS = ".hero-value, .hero-sub, .card .value, .watch-amount, .recent-amount, td.num, .rule-amount, " +
                ".bt-line, .trend-stats strong, .chart-box canvas, .split-note, .vb-value, .vb-amount";
  document.addEventListener("click", function (e) {
    if (!root.classList.contains("privacy")) return;
    var el = e.target.closest(AMOUNTS);
    if (!el || el.classList.contains("revealed")) return;
    e.preventDefault();
    e.stopPropagation();
    el.classList.add("revealed");
  }, true);
})();
