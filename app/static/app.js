// Charts. Data comes from JSON script tags, colours from the active theme's CSS variables.
(function () {
  if (typeof Chart === "undefined") return;
  var css = getComputedStyle(document.documentElement);
  function v(name) { return css.getPropertyValue(name).trim(); }
  function data(id) { var el = document.getElementById(id); return el ? JSON.parse(el.textContent) : null; }
  var eur = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" });
  Chart.defaults.color = v("--text-muted");
  Chart.defaults.borderColor = v("--chart-grid");
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;

  // Future-dated look: the category's colour as a light wash with thin diagonal stripes (the
  // usual "planned / not yet happened" hatching), so it reads as the same category but clearly
  // not spent yet. Falls back to a plain light tint if canvas patterns aren't available.
  function rgba(colour, a) {
    var c = document.createElement("canvas").getContext("2d");
    c.fillStyle = colour; var hex = c.fillStyle;           // normalises to #rrggbb
    if (hex.charAt(0) !== "#") return colour;
    var n = parseInt(hex.slice(1), 16);
    return "rgba(" + (n >> 16 & 255) + "," + (n >> 8 & 255) + "," + (n & 255) + "," + a + ")";
  }
  function faded(colour) {
    var size = 8, tile = document.createElement("canvas");
    tile.width = tile.height = size;
    var g = tile.getContext("2d");
    if (!g) return rgba(colour, 0.2);
    g.fillStyle = rgba(colour, 0.12);
    g.fillRect(0, 0, size, size);
    g.strokeStyle = rgba(colour, 0.55);
    g.lineWidth = 1.5;
    g.beginPath();                                          // "/" stripes that join across tiles
    g.moveTo(0, size); g.lineTo(size, 0);
    g.moveTo(-size / 2, size / 2); g.lineTo(size / 2, -size / 2);
    g.moveTo(size / 2, size * 1.5); g.lineTo(size * 1.5, size / 2);
    g.stroke();
    return g.createPattern(tile, "repeat") || rgba(colour, 0.2);
  }
  function anyValue(xs) { return xs.some(function (x) { return x; }); }

  // Spent vs income per period. Spent: what has happened, plus future-dated expenses faded on
  // top. Income: regular, plus extra income on top in its own colour.
  function spentVsIncome(canvasId, d) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;
    var spent = v("--chart-spent");
    var sets = [
      { label: "Spent", data: d.spent_past, backgroundColor: spent, stack: "spent" },
      { label: "Spent (future-dated)", data: d.spent_future, backgroundColor: faded(spent), stack: "spent",
        borderColor: spent, borderWidth: 1 },
      { label: "Regular income", data: d.regular, backgroundColor: v("--chart-income"), stack: "income" },
      { label: "Extra income", data: d.extra, backgroundColor: v("--chart-extra"), stack: "income" }
    ].filter(function (s, i) { return i % 2 === 0 || anyValue(s.data); });   // hide empty extras
    new Chart(canvas, {
      type: "bar",
      data: { labels: d.labels, datasets: sets },
      options: {
        maintainAspectRatio: false,
        scales: { x: { stacked: true },
                  y: { stacked: true, beginAtZero: true, ticks: { callback: function (x) { return eur.format(x); } } } },
        plugins: {
          legend: { position: "bottom" },
          tooltip: { callbacks: { label: function (c) { return c.dataset.label + ": " + eur.format(c.parsed.y); } } }
        }
      }
    });
  }

  // Year page
  var year = data("year-chart-data");
  if (year) spentVsIncome("year-chart", year);

  // Budget pace (Budget page): day-to-day spending vs the budget spread evenly;
  // the gap is green below, red above
  function budgetPace(bp) {
    var bpCanvas = document.getElementById("chart-budget-pace");
    if (bp && bpCanvas) {
      new Chart(bpCanvas, {
        type: "line",
        data: { labels: bp.labels, datasets: [
          { label: "Day-to-day spending", data: bp.actual, borderColor: v("--text"), backgroundColor: v("--text"),
            pointRadius: 0, borderWidth: 2.5, stepped: true,
            fill: { target: 1, above: rgba(v("--loss"), 0.3), below: rgba(v("--gain"), 0.3) } },
          { label: "Allowed by budget", data: bp.allowed, borderColor: v("--text-muted"), borderDash: [6, 5],
            pointRadius: 0, borderWidth: 1.5, fill: false }
        ] },
        options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
                   scales: { x: { title: { display: true, text: "Day of period" }, ticks: { maxTicksLimit: 8 } },
                             y: { beginAtZero: true, ticks: { callback: function (x) { return eur.format(x); } } } },
                   plugins: { legend: { position: "bottom" },
                              tooltip: { callbacks: { title: function (items) { return "Day " + items[0].label; },
                                                      label: function (c) { return c.dataset.label + ": " + eur.format(c.parsed.y); } } } } }
      });
    }
  }
  budgetPace(data("budget-pace-data"));    // the Budget page

  // Home page
  var dash = data("dashboard-data");
  if (dash) {
    spentVsIncome("chart-trend", dash.trend);

    var canvas = document.getElementById("chart-categories");
    if (canvas) {
      var palette = [];
      for (var i = 1; i <= 8; i++) palette.push(v("--cat-" + i));
      // Each category is one slice in its colour; its future-dated part is a faded slice next to it.
      // owner[k] = index of the category slice k belongs to (names can repeat, e.g. own + shared "Food").
      var cats = dash.categories, labels = [], amounts = [], colours = [], borders = [], futureSlice = [], owner = [];
      cats.labels.forEach(function (name, i) {
        var col = palette[i % palette.length], fut = (cats.future || [])[i] || 0;
        var past = Math.round((cats.amounts[i] - fut) * 100) / 100;
        function slice(amount, colour, border, future) {
          labels.push(name); amounts.push(amount); colours.push(colour); borders.push(border);
          futureSlice.push(future); owner.push(i);
        }
        if (past > 0) slice(past, col, v("--surface"), false);
        if (fut > 0) slice(fut, faded(col), col, true);
      });
      var total = amounts.reduce(function (a, b) { return a + b; }, 0);
      new Chart(canvas, {
        type: "doughnut",
        data: {
          labels: labels,
          datasets: [{ data: amounts, backgroundColor: colours, borderColor: borders, borderWidth: 2 }]
        },
        options: {
          maintainAspectRatio: false,
          cutout: "62%",
          plugins: {
            legend: { position: "bottom", labels: {
              boxWidth: 12, padding: 12,
              // one legend entry per category (its solid colour); clicking it hides both its slices
              generateLabels: function (chart) {
                return cats.labels.map(function (name, j) {
                  var first = owner.indexOf(j), col = palette[j % palette.length];
                  return { text: name, fillStyle: col, strokeStyle: col, lineWidth: 0, index: j,
                           hidden: !chart.getDataVisibility(first), fontColor: Chart.defaults.color };
                });
              } },
              onClick: function (e, item, legend) {
                var ch = legend.chart;
                owner.forEach(function (j, k) { if (j === item.index) ch.toggleDataVisibility(k); });
                ch.update();
              } },
            tooltip: { callbacks: { label: function (c) {
              return c.label + (futureSlice[c.dataIndex] ? " (future-dated)" : "") + ": " + eur.format(c.parsed) +
                     " (" + Math.round(c.parsed / total * 100) + "%)";
            } } }
          }
        }
      });
    }
  }

  // Trends page
  var tr = data("trends-data");
  if (tr) {
    var pct = function (x) { return x + "%"; };
    var savingsCanvas = document.getElementById("chart-savings");
    if (savingsCanvas) {
      var sets = [{ label: "Savings rate", data: tr.savings, borderColor: v("--chart-income"), backgroundColor: v("--chart-income"),
                    tension: 0.25, pointRadius: 3,
                    segment: { borderDash: function (c) { return c.p1DataIndex === tr.labels.length - 1 ? [5, 4] : undefined; } } }];
      if (tr.savings_avg !== null) {
        sets.push({ label: "Average", data: tr.labels.map(function () { return tr.savings_avg; }),
                    borderColor: v("--text-muted"), borderDash: [6, 5], borderWidth: 1.5, pointRadius: 0 });
      }
      new Chart(savingsCanvas, {
        type: "line", data: { labels: tr.labels, datasets: sets },
        options: { maintainAspectRatio: false, scales: { y: { ticks: { callback: pct } } },
                   plugins: { legend: { position: "bottom" },
                              tooltip: { callbacks: { label: function (c) { return c.dataset.label + ": " + c.parsed.y + "%"; } } } } }
      });
    }

    var catCanvas = document.getElementById("chart-categories-trend");
    if (catCanvas) {
      var pal = [];
      for (var k = 1; k <= 8; k++) pal.push(v("--cat-" + k));
      new Chart(catCanvas, {
        type: "line",
        data: { labels: tr.labels, datasets: tr.categories.map(function (c, i) {
          return { label: c.name, data: c.values, hidden: c.hidden, tension: 0.25, pointRadius: 2,
                   borderColor: pal[i % pal.length], backgroundColor: pal[i % pal.length] };
        }) },
        options: { maintainAspectRatio: false,
                   scales: { y: { beginAtZero: true, ticks: { callback: function (x) { return eur.format(x); } } } },
                   plugins: { legend: { position: "bottom", labels: { boxWidth: 12, padding: 10 } },
                              tooltip: { callbacks: { label: function (c) { return c.dataset.label + ": " + eur.format(c.parsed.y); } } } } }
      });
    }

    var paceCanvas = document.getElementById("chart-pace");
    if (paceCanvas && tr.pace.typical) {
      new Chart(paceCanvas, {
        type: "line",
        data: { labels: tr.pace.labels, datasets: [
          { label: "This period", data: tr.pace.current, borderColor: v("--chart-income"), backgroundColor: v("--chart-income"),
            pointRadius: 0, borderWidth: 2.5, stepped: true },
          { label: "Usual", data: tr.pace.typical, borderColor: v("--text-muted"), borderDash: [6, 5],
            pointRadius: 0, borderWidth: 1.5, stepped: true }
        ] },
        options: { maintainAspectRatio: false,
                   scales: { x: { title: { display: true, text: "Day of period" }, ticks: { maxTicksLimit: 8 } },
                             y: { beginAtZero: true, ticks: { callback: function (x) { return eur.format(x); } } } },
                   plugins: { legend: { position: "bottom" },
                              tooltip: { callbacks: { title: function (items) { return "Day " + items[0].label; },
                                                      label: function (c) { return c.dataset.label + ": " + eur.format(c.parsed.y); } } } } }
      });
    }
  }

  // Plans page: projected savings over the next periods
  var fcd = data("forecast-data");
  var fcCanvas = document.getElementById("chart-forecast");
  if (fcd && fcCanvas) {
    new Chart(fcCanvas, {
      type: "line",
      data: { labels: fcd.labels, datasets: [
        { label: "If spending stays typical", data: fcd.typical, borderColor: v("--chart-income"),
          backgroundColor: v("--chart-income"), tension: 0.2, pointRadius: 2 },
        { label: "Cautious (pricier periods)", data: fcd.cautious, borderColor: v("--text-muted"),
          borderDash: [6, 5], tension: 0.2, pointRadius: 0 }
      ] },
      options: { maintainAspectRatio: false,
                 scales: { y: { ticks: { callback: function (x) { return eur.format(x); } } } },
                 plugins: { legend: { position: "bottom" },
                            tooltip: { callbacks: { label: function (c) { return c.dataset.label + ": " + eur.format(c.parsed.y); } } } } }
    });
  }
})();
