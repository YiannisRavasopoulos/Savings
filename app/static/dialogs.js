// Pop-up dialogs: open with [data-open="id"], close with [data-close] or Esc / tapping outside.
// After a server-side error the page names the dialog to reopen (data-reopen), and an error
// pop-up marked [data-autoshow] opens on load.
(function () {
  function open(id) {
    var d = document.getElementById(id);
    if (d && !d.open) d.showModal();
  }

  document.addEventListener("click", function (e) {
    var opener = e.target.closest("[data-open]");
    if (opener) { open(opener.getAttribute("data-open")); return; }
    var closer = e.target.closest("[data-close]");
    if (closer) { closer.closest("dialog").close(); return; }
    if (e.target.tagName === "DIALOG") e.target.close();   // tap on the backdrop
  });

  // Delete dialogs: only the chosen option's fields are active.
  document.querySelectorAll("[data-delete-form]").forEach(function (form) {
    function sync() {
      var chosen = form.querySelector('input[name="action"]:checked');
      form.querySelectorAll(".choice-detail").forEach(function (box) {
        var on = chosen && box.getAttribute("data-for") === chosen.value;
        box.hidden = !on;
        box.querySelectorAll("input, select").forEach(function (el) { el.disabled = !on; });
      });
    }
    form.addEventListener("change", sync);
    sync();
  });

  var script = document.currentScript;
  var reopen = script && script.getAttribute("data-reopen");
  if (reopen) open(reopen);
  document.querySelectorAll("dialog[data-autoshow]").forEach(function (d) { d.showModal(); });
})();
