// Sets the theme before first paint: a stored override, otherwise the system setting.
// Loaded as a plain file so the page needs no inline script. Keep in step with src/ThemeToggle.tsx.
(function () {
  var root = document.documentElement;
  var stored = null;
  try {
    stored = window.localStorage.getItem("theme");
  } catch (e) {}
  var override = stored === "light" || stored === "dark";
  var theme = override ? stored : window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  root.dataset.theme = theme;
  if (override) {
    var color = theme === "dark" ? "#262624" : "#faf9f5";
    var metas = document.querySelectorAll('meta[name="theme-color"]');
    for (var i = 0; i < metas.length; i++) metas[i].content = color;
  }
})();
