/*
 * FDE · Assignment 1 · Extension content bootstrap  (PROVIDED)
 * -----------------------------------------------------------
 * Runs BEFORE translation-widget.js (see manifest content_scripts order).
 * Two jobs:
 *   1. Read the saved backend URL from chrome.storage and expose it as
 *      window.FDE_CONFIG so the widget picks it up on load.
 *   2. Relay popup commands (translate page / restore / open) to the widget
 *      via window events.
 */
(function () {
  try {
    chrome.storage.sync.get({ apiUrl: "http://localhost:8787" }, (cfg) => {
      window.FDE_CONFIG = Object.assign({}, window.FDE_CONFIG, { API_URL: cfg.apiUrl });
      // LOCAL PATCH: chrome.storage.sync.get is async, but translation-widget.js
      // reads window.FDE_CONFIG synchronously at parse time (same content_scripts
      // batch), so it almost always wins the race and freezes on the localhost
      // default. Signal the widget once the real value is known so it can patch
      // itself — see the matching listener added in translation-widget.js.
      window.dispatchEvent(new CustomEvent("FDE_CONFIG_READY", { detail: { apiUrl: cfg.apiUrl } }));
    });
  } catch (_) {
    /* storage not available; widget falls back to its default */
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (!msg || !msg.type) return;
    if (msg.type === "TRANSLATE_PAGE") window.dispatchEvent(new Event("FDE_TRANSLATE_PAGE"));
    if (msg.type === "RESTORE_PAGE") window.dispatchEvent(new Event("FDE_RESTORE_PAGE"));
    if (msg.type === "OPEN") window.dispatchEvent(new Event("FDE_OPEN"));
  });
})();
