"use strict";

(() => {
  const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
  const root = document.querySelector(".main-content, .login-layout, .signup-layout, #content");
  if (!root || typeof Element.prototype.animate !== "function") return;
  const animations = new Set();
  const seen = new WeakSet();
  const ease = "cubic-bezier(.22, .75, .25, 1)";
  const revealSelector = [
    ".page-heading", ".messages > .toast", ".stat-card", ".panel", ".pc-card", ".component-card",
    ".recommendation-card", ".technician-card", ".admin-rule-card", ".form-section",
    ".history-record", ".appointment-card", ".feedback-card", ".empty-state",
    ".login-story", ".login-form-wrap", ".signup-story", ".signup-card",
    "#content > h1", "#content-main > .module"
  ].join(", ");
  const chartSelector = ".chart-bar, .rating-distribution meter";
  let observer;

  function play(element, frames, options = {}) {
    if (preference.matches || document.hidden || !element.isConnected || element.contains(document.activeElement)) return;
    const animation = element.animate(frames, {duration: 440, easing: ease, fill: "backwards", ...options});
    const item = {element, animation};
    animations.add(item);
    animation.onfinish = animation.oncancel = () => animations.delete(item);
  }

  function finishAnimations() {
    [...animations].forEach(({animation}) => animation.finish());
  }

  function reveal(element, delay = 0) {
    if (seen.has(element)) return;
    seen.add(element);
    if (element.matches(chartSelector)) {
      const vertical = element.classList.contains("chart-bar");
      play(element, [
        {transform: vertical ? "scaleY(0)" : "scaleX(0)", transformOrigin: vertical ? "center bottom" : "left center"},
        {transform: vertical ? "scaleY(1)" : "scaleX(1)", transformOrigin: vertical ? "center bottom" : "left center"}
      ], {duration: 650, delay});
    } else {
      play(element, [{opacity: 0, transform: "translateY(12px)"}, {opacity: 1, transform: "translateY(0)"}], {delay});
    }
  }

  function setup() {
    document.documentElement.dataset.motion = preference.matches ? "reduced" : "enabled";
    observer?.disconnect();
    if (preference.matches) {
      finishAnimations();
      return;
    }
    // Animate only outer containers, keeping nested cards and fields steady.
    const containers = [...root.querySelectorAll(revealSelector)].filter(element => !element.parentElement.closest(revealSelector));
    const targets = [...containers, ...root.querySelectorAll(chartSelector)].filter(element => !seen.has(element));
    if (!("IntersectionObserver" in window)) {
      targets.forEach(element => reveal(element));
      return;
    }
    observer = new IntersectionObserver(entries => {
      let order = 0;
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        observer.unobserve(entry.target);
        reveal(entry.target, Math.min(order++, 5) * 45);
      });
    }, {rootMargin: "0px 0px 12px 0px", threshold: 0});
    targets.forEach(element => observer.observe(element));
  }

  // Native form submission and validation retain their normal behaviour.
  document.addEventListener("submit", event => {
    if (event.defaultPrevented) return;
    const button = event.submitter || event.target.querySelector('[data-submit-label], button[type="submit"], button:not([type])');
    if (!button?.classList.contains("button")) return;
    button.classList.add("is-pending");
    button.setAttribute("aria-busy", "true");
  });
  window.addEventListener("pageshow", () => {
    document.querySelectorAll(".button.is-pending").forEach(button => {
      button.classList.remove("is-pending");
      button.removeAttribute("aria-busy");
    });
  });
  document.addEventListener("focusin", event => {
    [...animations].forEach(({element, animation}) => {
      if (element.contains(event.target)) animation.finish();
    });
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) finishAnimations();
  });
  document.addEventListener("toggle", event => {
    if (event.target.matches("details.faq-item[open]")) {
      const answer = event.target.querySelector(".faq-answer");
      if (answer) play(answer, [{opacity: .3, transform: "translateY(-4px)"}, {opacity: 1, transform: "translateY(0)"}], {duration: 220});
    }
  }, true);

  const bell = document.querySelector("[data-notification-bell]");
  const badge = bell?.querySelector("[data-notification-count]");
  if (badge) {
    let previous = Number.parseInt(badge.textContent, 10) || 0;
    new MutationObserver(() => {
      const count = Number.parseInt(badge.textContent, 10) || 0;
      if (count > previous) {
        play(badge, [{transform: "scale(1)"}, {transform: "scale(1.18)"}, {transform: "scale(1)"}], {duration: 350});
        const icon = bell.querySelector(".icon");
        if (icon) play(icon, [{transform: "rotate(0)"}, {transform: "rotate(-9deg)"}, {transform: "rotate(7deg)"}, {transform: "rotate(0)"}], {duration: 420});
      }
      previous = count;
    }).observe(badge, {childList: true, characterData: true, subtree: true});
  }

  // A small observer handles newly inserted messages and form rows only.
  new MutationObserver(records => {
    records.forEach(record => record.addedNodes.forEach(node => {
      if (!(node instanceof Element)) return;
      const selector = ".toast, .notification-live-toast, [data-part-row]";
      const fresh = node.matches(selector) ? [node] : [...node.querySelectorAll(selector)];
      fresh.forEach(element => {
        if (seen.has(element)) return;
        seen.add(element);
        play(element, [{opacity: .3, transform: "translateY(7px)"}, {opacity: 1, transform: "translateY(0)"}], {duration: 250});
      });
    }));
  }).observe(document.body, {childList: true, subtree: true});

  preference.addEventListener("change", setup);
  setup();
})();
