// Effects: a red "damage" pulse when money goes out, a green "life gain" glow when it comes in.
// Plays after saving an expense or income (full forms and quick add).
// Off when the device asks for reduced motion or Settings → Appearance → Animations is off
// (both set html.no-anim, see base.html).
(function () {
  var root = document.documentElement;
  var eur = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" });
  function enabled() { return !root.classList.contains("no-anim"); }

  function once(el, cls) {
    el.classList.remove(cls);
    void el.offsetWidth;                 // restart the animation if it's already there
    el.classList.add(cls);
    el.addEventListener("animationend", function () { el.classList.remove(cls); }, { once: true });
  }

  function aura(kind) {
    var a = document.createElement("div");
    a.className = "fx-aura fx-aura-" + kind;
    a.setAttribute("aria-hidden", "true");
    document.body.appendChild(a);
    a.addEventListener("animationend", function () { a.remove(); });
  }

  function floatText(text, kind, anchor) {
    var f = document.createElement("div");
    f.className = "fx-float fx-float-" + kind;
    f.setAttribute("aria-hidden", "true");
    f.textContent = text;
    var r = anchor ? anchor.getBoundingClientRect() : null;
    var top = r && r.bottom > 0 && r.top < innerHeight ? r.top : innerHeight * 0.35;
    var left = r && r.bottom > 0 && r.top < innerHeight ? r.left + r.width / 2 : innerWidth / 2;
    f.style.top = top + "px";
    f.style.left = left + "px";
    document.body.appendChild(f);
    f.addEventListener("animationend", function () { f.remove(); });
  }

  function countTo(el, from, to, ms) {
    var start = null;
    function frame(t) {
      if (start === null) start = t;
      var p = Math.min(1, (t - start) / ms), e = 1 - Math.pow(1 - p, 3);   // ease-out
      el.textContent = eur.format((from + (to - from) * e) / 100);
      if (p < 1) requestAnimationFrame(frame);
    }
    el.textContent = eur.format(from / 100);
    requestAnimationFrame(frame);
  }

  // kind: "damage" (money out) or "heal" (money in); cents: the amount
  function play(kind, cents) {
    if (!enabled() || !cents) return;
    var main = document.querySelector("main");
    aura(kind);
    if (main) once(main, kind === "damage" ? "fx-shake" : "fx-lift");
    var hero = document.querySelector(".hero-value[data-cents]");
    var marker = document.querySelector("[data-fx]");
    // Home: from "Left over"; the Add pages: from the top, where the "Saved." banner used to be
    var anchor = hero || (marker && marker.offsetWidth > 2 ? marker : null) || document.querySelector("main h1");
    floatText((kind === "damage" ? "−" : "+") + eur.format(cents / 100), kind, anchor);
    if (hero) {                           // Home: "Left over" ticks from the old value to the new one
      var now = parseInt(hero.getAttribute("data-cents"), 10);
      countTo(hero, kind === "damage" ? now + cents : now - cents, now, 750);
    }
  }
  window.savingsFx = { play: play };

  function start() {
    // after quick add (set before the page reloaded)
    var queued = null;
    try { queued = JSON.parse(sessionStorage.getItem("savings-fx") || "null"); sessionStorage.removeItem("savings-fx"); }
    catch (e) { queued = null; }
    if (queued) { play(queued.kind, queued.cents); return; }
    // after the full Add expense / Add income forms ("Saved." carries the effect)
    var marker = document.querySelector("[data-fx]");
    if (marker) {
      play(marker.getAttribute("data-fx"), parseInt(marker.getAttribute("data-fx-cents"), 10) || 0);
      // a refresh shouldn't replay it: drop the amount from the address
      var url = new URL(location.href);
      if (url.searchParams.has("amt")) { url.searchParams.delete("amt"); history.replaceState(history.state, "", url); }
    }
  }
  // Splash: tap to skip; when it ends, take it out of the way. play() replays any splash
  // (Settings → Appearance → Play, and ./preview-splashes.sh).
  function wire(el, done) {
    el.addEventListener("click", function () { el.classList.add("splash-skip"); });
    el.addEventListener("animationend", function (e) {
      if (e.target !== el || e.animationName !== "splash-out") return;
      root.classList.remove("splash");
      if (done) done();
    });
  }
  window.savingsSplash = {
    play: function (name, note, done) {
      var old = document.getElementById("splash");
      if (!old) return;
      var fresh = old.cloneNode(true);             // a fresh copy restarts every animation
      fresh.classList.remove("splash-skip");
      fresh.querySelector(".sp-note").textContent = note || "";
      root.classList.remove("splash");
      root.setAttribute("data-splash", name);
      old.replaceWith(fresh);
      void fresh.offsetWidth;
      root.classList.add("splash");
      wire(fresh, done);
    }
  };

  var splash = document.getElementById("splash");
  if (splash && root.classList.contains("splash")) {
    // wait for the splash so the effect isn't hidden behind it
    var started = false;
    var go = function () { if (!started) { started = true; start(); } };
    wire(splash, go);
    setTimeout(go, 4000);
  } else {
    if (splash) wire(splash);
    start();
  }
})();
