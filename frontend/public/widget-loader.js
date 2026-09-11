/**
 * Campus-AI embeddable widget loader.
 *
 * A university pastes this into its own site:
 *
 *   <script src="https://campus-ai.app/widget-loader.js" data-widget-key="pk_tue_..."></script>
 *
 * See ARCHITECTURE.md §8 for the full reasoning. Two things this file is deliberately built to
 * be, because it runs inside every visitor's page load on someone else's website:
 *
 *   1. Tiny and dependency-free (vanilla JS, no framework, no build step to consume it).
 *   2. CSS-isolated from the host page in both pieces it renders: the floating trigger button
 *      (rendered into a ShadowRoot, since it lives directly in the host page's DOM) and the
 *      chat panel itself (an <iframe> pointed at the actual chat UI, which runs in its own
 *      document/origin and can't collide with -- or be broken by -- the host page's CSS/JS at
 *      all).
 *
 * This file intentionally does NOT read or store the widget key anywhere but in this closure --
 * it's already public (safe to be visible in the host page's HTML, per ARCHITECTURE.md §7), so
 * there's nothing to protect here beyond not leaking it somewhere *more* persistent than the
 * script tag it already lives in (e.g. never written to localStorage/cookies on the host page).
 */
(function () {
  "use strict";

  var currentScript = document.currentScript;
  if (!currentScript) return;

  var widgetKey = currentScript.getAttribute("data-widget-key");
  if (!widgetKey) {
    console.error("[campus-ai] widget-loader.js: missing required data-widget-key attribute.");
    return;
  }

  // The origin the loader itself was served from is the origin the widget page and API also
  // live on in this deployment (see ARCHITECTURE.md §9 -- one Next.js app serves both the
  // loader and the widget page). data-base-url overrides this for local development against a
  // backend/frontend running on different ports.
  var baseUrl =
    currentScript.getAttribute("data-base-url") ||
    (currentScript.src ? new URL(currentScript.src).origin : "");

  var OPEN_WIDTH = 380;
  var OPEN_HEIGHT = 560;
  var BUBBLE_SIZE = 56;

  var host = document.createElement("div");
  host.id = "campus-ai-widget-host";
  host.style.all = "initial"; // isolate from any host page CSS that targets this element itself
  document.body.appendChild(host);

  var shadow = host.attachShadow({ mode: "open" });

  var style = document.createElement("style");
  style.textContent = [
    ":host { all: initial; }",
    ".bubble {",
    "  position: fixed; bottom: 20px; right: 20px; width: " + BUBBLE_SIZE + "px; height: " + BUBBLE_SIZE + "px;",
    "  border-radius: 50%; background: #171717; color: #fff; border: none; cursor: pointer;",
    "  box-shadow: 0 4px 14px rgba(0,0,0,0.25); font-size: 24px; z-index: 2147483000;",
    "  display: flex; align-items: center; justify-content: center;",
    "}",
    ".panel {",
    "  position: fixed; bottom: 88px; right: 20px; width: " + OPEN_WIDTH + "px; height: " + OPEN_HEIGHT + "px;",
    "  max-width: calc(100vw - 40px); max-height: calc(100vh - 110px);",
    "  border-radius: 16px; overflow: hidden; box-shadow: 0 10px 40px rgba(0,0,0,0.3);",
    "  z-index: 2147483000; display: none;",
    "}",
    ".panel.open { display: block; }",
    "iframe { width: 100%; height: 100%; border: none; }",
  ].join("\n");
  shadow.appendChild(style);

  var bubble = document.createElement("button");
  bubble.className = "bubble";
  bubble.setAttribute("aria-label", "Open chat");
  bubble.textContent = "💬";
  shadow.appendChild(bubble);

  var panel = document.createElement("div");
  panel.className = "panel";
  shadow.appendChild(panel);

  var iframe = null;
  var isOpen = false;

  bubble.addEventListener("click", function () {
    isOpen = !isOpen;
    panel.classList.toggle("open", isOpen);
    if (isOpen && !iframe) {
      iframe = document.createElement("iframe");
      iframe.src = baseUrl + "/widget?key=" + encodeURIComponent(widgetKey);
      iframe.title = "Campus-AI chat";
      panel.appendChild(iframe);
    }
    bubble.textContent = isOpen ? "✕" : "💬";
  });
})();
