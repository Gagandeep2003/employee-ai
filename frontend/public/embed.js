/**
 * AI Employee embed loader.
 *
 * Usage on a customer's website (that's the whole install -- one line, no build
 * step, works on any site regardless of what it's built with):
 *
 *   <script src="https://yourapp.com/embed.js" data-business="biz_xxx" async></script>
 *
 * This creates a small floating <iframe> pointing at the widget route
 * (ChatWidget.jsx, served by the React app) and resizes it in response to
 * postMessage size reports from that iframe -- so it only ever covers the
 * bubble/chat window itself, never the whole page, and the rest of the host
 * site stays fully clickable.
 */
(function () {
  "use strict";

  var scriptEl = document.currentScript || (function () {
    var scripts = document.getElementsByTagName("script");
    return scripts[scripts.length - 1];
  })();

  var businessId = scriptEl.getAttribute("data-business");
  if (!businessId) {
    console.error("[AI Employee] Missing data-business attribute on the embed <script> tag.");
    return;
  }

  // Defaults to the origin this script was loaded from, so a single build works
  // for every customer without hardcoding a domain. Override with data-origin
  // if you're serving embed.js from a CDN separate from the app itself.
  var origin = scriptEl.getAttribute("data-origin");
  if (!origin) {
    var src = scriptEl.src || "";
    var m = src.match(/^(https?:\/\/[^/]+)/);
    origin = m ? m[1] : window.location.origin;
  }
  var position = scriptEl.getAttribute("data-position") || "bottom-right";

  var iframe = document.createElement("iframe");
  iframe.src = origin + "/widget/" + encodeURIComponent(businessId);
  iframe.title = "Chat with us";
  iframe.setAttribute("aria-label", "Chat widget");
  iframe.style.position = "fixed";
  iframe.style.bottom = "0";
  iframe.style[position.indexOf("left") !== -1 ? "left" : "right"] = "0";
  iframe.style.width = "96px";
  iframe.style.height = "96px";
  iframe.style.border = "none";
  iframe.style.background = "transparent";
  iframe.style.zIndex = "2147483000";
  iframe.style.colorScheme = "light";
  iframe.style.transition = "width 0.15s ease, height 0.15s ease";
  iframe.allow = "clipboard-write";

  document.addEventListener("DOMContentLoaded", mount);
  if (document.readyState === "complete" || document.readyState === "interactive") mount();

  function mount() {
    if (document.body && !document.body.contains(iframe)) {
      document.body.appendChild(iframe);
    }
  }

  window.addEventListener("message", function (event) {
    if (event.origin !== origin) return;
    if (!event.data || event.data.source !== "ai-employee-widget") return;
    if (event.data.type === "size") {
      var w = Math.max(1, Math.min(600, event.data.width | 0));
      var h = Math.max(1, Math.min(800, event.data.height | 0));
      iframe.style.width = w + "px";
      iframe.style.height = h + "px";
    }
  });
})();
