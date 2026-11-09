// Quick add (phone only): the ⚡ menu's "Add expense" opens a bottom sheet instead of the full
// page. On a wider screen, or if anything fails to load, the link simply opens /add as before.
// After saving, the page reloads (so totals are fresh) and the red / green effect confirms it.
(function () {
  var link = document.querySelector("[data-quick-add]");
  var dlg = document.getElementById("quick-add");
  if (!link || !dlg || typeof dlg.showModal !== "function") return;
  var phone = window.matchMedia("(max-width: 699px)");
  var form = document.getElementById("qa-form");
  var amount = document.getElementById("qa-amount");
  var cats = document.getElementById("qa-cats");
  var more = document.getElementById("qa-more");
  var catInput = document.getElementById("qa-category");
  var dateInput = document.getElementById("qa-date");
  var desc = document.getElementById("qa-description");
  var full = document.getElementById("qa-full");
  var save = form.querySelector(".qa-save");
  var data = null, busy = false;

  function kind() { return form.querySelector("input[name=kind]:checked").value; }

  function showErrors(errors) {
    form.querySelectorAll("[data-qa-error]").forEach(function (el) {
      var msg = errors && errors[el.getAttribute("data-qa-error")];
      el.textContent = msg || "";
      el.hidden = !msg;
    });
  }

  function pickCategory(id) {
    catInput.value = id ? String(id) : "";
    cats.querySelectorAll(".qa-chip").forEach(function (b) {
      var on = b.getAttribute("data-id") === catInput.value;
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-checked", on ? "true" : "false");
    });
    var inTop = !!cats.querySelector('.qa-chip[data-id="' + catInput.value + '"]');
    more.value = inTop ? "" : catInput.value;
    more.classList.toggle("is-on", !inTop && !!catInput.value);
  }

  function pickDay(iso) {
    dateInput.value = iso;
    form.querySelectorAll("[data-qa-day]").forEach(function (b) {
      var on = data && data[b.getAttribute("data-qa-day")] === iso;
      b.classList.toggle("is-on", on);
    });
  }

  function syncKind() {
    var income = kind() === "income";
    form.querySelector("[data-qa-expense]").hidden = income;
    full.href = income ? "/income#add-income" : "/add";
    save.textContent = income ? "Save income" : "Save expense";
    showErrors(null);
  }

  function build(d) {
    data = d;
    cats.innerHTML = "";
    more.length = 1;
    var byId = {};
    d.categories.forEach(function (c) { byId[c.id] = c; });
    d.top.forEach(function (id) {
      var c = byId[id];
      if (!c) return;
      var b = document.createElement("button");
      b.type = "button";
      b.className = "qa-chip" + (c.joint ? " is-joint" : "");
      b.setAttribute("role", "radio");
      b.setAttribute("data-id", c.id);
      b.textContent = (c.joint ? "◆ " : "") + c.name;
      b.addEventListener("click", function () { pickCategory(c.id); });
      cats.appendChild(b);
    });
    d.categories.forEach(function (c) {
      if (d.top.indexOf(c.id) >= 0) return;
      var o = document.createElement("option");
      o.value = c.id;
      o.textContent = (c.joint ? "◆ " : "") + c.name;
      more.appendChild(o);
    });
    more.hidden = more.length <= 1;
    pickCategory(d.last);
    pickDay(d.today);
  }

  function open() {
    form.reset();
    showErrors(null);
    syncKind();
    dlg.showModal();
    if (window.scrollLock) window.scrollLock.lock();
    amount.focus();                        // inside the tap, so the phone's keypad opens
    fetch("/quick-add/data", { credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(build)
      .catch(function () { location.href = "/add"; });   // fall back to the full page
  }

  link.addEventListener("click", function (e) {
    if (!phone.matches) return;            // phone only: elsewhere the link opens /add
    e.preventDefault();
    var menu = link.closest("details");
    if (menu) menu.open = false;
    open();
  });

  form.querySelectorAll("input[name=kind]").forEach(function (r) { r.addEventListener("change", syncKind); });
  more.addEventListener("change", function () { pickCategory(more.value); });
  form.querySelectorAll("[data-qa-day]").forEach(function (b) {
    b.addEventListener("click", function () { if (data) pickDay(data[b.getAttribute("data-qa-day")]); });
  });
  dateInput.addEventListener("change", function () { pickDay(dateInput.value); });
  dlg.addEventListener("close", function () { if (window.scrollLock) window.scrollLock.unlock(); });
  dlg.querySelector("[data-qa-close]").addEventListener("click", function () { dlg.close(); });
  dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });   // tap on the backdrop

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (busy) return;
    if (kind() === "expense" && !catInput.value) { showErrors({ category_id: "Pick a category." }); return; }
    busy = true;
    save.disabled = true;
    var body = new FormData(form);
    if (kind() === "income") body.delete("category_id");
    fetch("/quick-add", { method: "POST", body: body, credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok) { showErrors(res.j.errors || { amount: "Couldn't save. Try again." }); return; }
        try {
          sessionStorage.setItem("savings-fx", JSON.stringify({ kind: res.j.kind === "income" ? "heal" : "damage", cents: res.j.cents }));
        } catch (err) { /* private mode */ }
        location.reload();
      })
      .catch(function () { showErrors({ amount: "Couldn't reach the server. Nothing was saved." }); })
      .then(function () { busy = false; save.disabled = false; });
  });

})();
