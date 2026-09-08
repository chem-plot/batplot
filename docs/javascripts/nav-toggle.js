/**
 * Docs-only: click the active chapter title in the left sidebar again to
 * collapse / expand its in-page TOC dropdown (toc.integrate).
 */
(function () {
  function setupToggle(link) {
    var item = link.closest(".md-nav__item");
    if (!item) return;
    // Nested nav that lists this page's headings
    var nested = null;
    for (var i = 0; i < item.children.length; i++) {
      var child = item.children[i];
      if (child.classList && child.classList.contains("md-nav")) {
        nested = child;
        break;
      }
    }
    if (!nested) return;

    link.setAttribute("aria-expanded", nested.classList.contains("bp-nav-collapsed") ? "false" : "true");
    link.setAttribute("title", "Click to show or hide this chapter’s sections");

    link.addEventListener("click", function (ev) {
      // Only toggle when this link is the current page (already active).
      if (!link.classList.contains("md-nav__link--active")) return;
      ev.preventDefault();
      ev.stopPropagation();
      var collapsed = nested.classList.toggle("bp-nav-collapsed");
      link.setAttribute("aria-expanded", collapsed ? "false" : "true");
    });
  }

  function init() {
    document
      .querySelectorAll(".md-nav--primary .md-nav__item--active > .md-nav__link--active")
      .forEach(setupToggle);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Material may reinject nav on instant navigation
  document.addEventListener("DOMContentLoaded", function () {
    var observer = new MutationObserver(function () {
      document
        .querySelectorAll(
          ".md-nav--primary .md-nav__item--active > .md-nav__link--active:not([aria-expanded])"
        )
        .forEach(setupToggle);
    });
    var root = document.querySelector(".md-sidebar--primary");
    if (root) observer.observe(root, { childList: true, subtree: true });
  });
})();
