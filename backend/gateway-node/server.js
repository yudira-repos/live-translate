/*
 * FDE · Assignment 1 · Node Gateway  (the "software backend")
 * ==========================================================
 * This is the ONLY server the browser widget talks to. Its jobs:
 *   - serve the widget file at /widget.js
 *   - accept translation requests from the widget (CORS, validation)
 *   - forward them to the Python AI service
 *   - expose /health and /stats
 *   - log every request
 *
 * It is ~90% done. Find the two `TODO (YOU)` blocks and implement them.
 * Everything else works out of the box.
 *
 * Run:  npm install && npm start      (needs Node 18+ for global fetch)
 */
const express = require("express");
const cors = require("cors");
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
require("dotenv").config();

const PORT = process.env.PORT || 8787;
const AI_SERVICE_URL = process.env.AI_SERVICE_URL || "http://localhost:8000";
const LOG_FILE = path.join(__dirname, "gateway.log");

// Local dev: the full repo is checked out, so the widget lives two dirs up.
// Deployed (Fly.io): Docker's build context is just this directory, so
// `predeploy.sh` vendors a copy into ./widget/ first — prefer that if present.
const WIDGET_CANDIDATES = [
  path.join(__dirname, "widget", "translation-widget.js"),
  path.join(__dirname, "..", "..", "widget", "translation-widget.js"),
];
const WIDGET_PATH = WIDGET_CANDIDATES.find((p) => fs.existsSync(p)) || WIDGET_CANDIDATES[1];

const app = express();
const startedAt = Date.now();

// --- structured logging: one JSON line per event, to stdout AND gateway.log ---
function logLine(event, fields) {
  const record = { ts: new Date().toISOString(), level: "INFO", event, ...fields };
  const line = JSON.stringify(record);
  console.log(line);
  try {
    fs.appendFileSync(LOG_FILE, line + "\n");
  } catch (_) {
    // best-effort file logging; never let it take the request down
  }
}

// --- middleware ----------------------------------------------------------
app.use(cors()); // dev: allow every origin so the widget works on any page
app.use(express.json({ limit: "1mb" }));

// --- request id: reuse an inbound X-Request-Id, else generate one --------
// This is what lets one request be greppable end-to-end across both services.
app.use((req, res, next) => {
  req.requestId = req.get("X-Request-Id") || crypto.randomUUID();
  res.set("X-Request-Id", req.requestId);
  next();
});

/*
 * TODO (YOU) #1 — request logging middleware. DONE.
 * Logs one structured line per request AFTER it finishes: method, url,
 * status code, duration in ms, and the request id for trace correlation.
 */
app.use((req, res, next) => {
  const t0 = Date.now();
  res.on("finish", () => {
    logLine("request", {
      requestId: req.requestId,
      method: req.method,
      url: req.originalUrl,
      status: res.statusCode,
      durationMs: Date.now() - t0,
    });
  });
  next();
});

// --- serve the widget to the console loader ------------------------------
app.get("/widget.js", (req, res) => {
  res.type("application/javascript");
  res.sendFile(WIDGET_PATH);
});

// --- helper: forward a request to the Python AI service ------------------
/*
 * TODO (YOU) #2 — the proxy call. DONE.
 * POSTs `body` as JSON to `${AI_SERVICE_URL}${path}`, forwarding the request
 * id so the AI service logs the same trace id, and returns the parsed JSON
 * response. Throws on a non-2xx so callers turn it into a 502.
 */
async function callAiService(path, body, requestId) {
  const res = await fetch(AI_SERVICE_URL + path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(requestId ? { "X-Request-Id": requestId } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`AI service ${res.status}${detail ? `: ${detail}` : ""}`);
  }
  return res.json();
}

// --- routes the widget calls ---------------------------------------------
app.post("/translate", async (req, res) => {
  const { text, target } = req.body || {};
  if (typeof text !== "string") return res.status(400).json({ error: "`text` (string) is required" });
  try {
    const data = await callAiService("/translate", { text, target: target || "es-MX" }, req.requestId);
    res.json(data);
  } catch (err) {
    res.status(502).json({ error: "AI service error: " + err.message });
  }
});

app.post("/translate/batch", async (req, res) => {
  const { texts, target } = req.body || {};
  if (!Array.isArray(texts)) return res.status(400).json({ error: "`texts` (array) is required" });
  try {
    const data = await callAiService("/translate/batch", { texts, target: target || "es-MX" }, req.requestId);
    res.json(data);
  } catch (err) {
    res.status(502).json({ error: "AI service error: " + err.message });
  }
});

app.get("/health", async (req, res) => {
  const uptimeSec = Math.round((Date.now() - startedAt) / 1000);
  let ai = "unreachable";
  try {
    const r = await fetch(AI_SERVICE_URL + "/health");
    ai = r.ok ? await r.json() : "error";
  } catch (_) {}
  res.json({ status: "ok", gatewayUptimeSec: uptimeSec, aiService: ai });
});

app.get("/stats", async (req, res) => {
  try {
    const r = await fetch(AI_SERVICE_URL + "/stats");
    res.json(await r.json());
  } catch (err) {
    res.status(502).json({ error: "AI service error: " + err.message });
  }
});

app.listen(PORT, () => {
  console.log(`FDE gateway on http://localhost:${PORT}  →  AI service ${AI_SERVICE_URL}`);
  console.log(`Widget served at http://localhost:${PORT}/widget.js`);
});
