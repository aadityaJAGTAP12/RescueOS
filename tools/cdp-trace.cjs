// TEMPORARY diagnostic (NOT production code): CDP Network tracing of the
// analyze-need request lifecycle through the Vite proxy. Reports Chrome's
// queueing/stalled/proxy phases for each /api request.
const puppeteer = require("puppeteer");

const BASE = "http://localhost:3000";
const TAG = `diag-${Date.now()}`;
const NEED_TITLE = `Verify boat evacuation ${TAG}`;

async function api(path, options = {}) {
  const resp = await fetch(`http://localhost:5001${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  return resp.status;
}

async function run() {
  await api("/api/organizations", {
    method: "POST",
    body: JSON.stringify({ id: "org_demo", name: "Demo Relief Org", organization_type: "ngo" }),
  });
  await api("/api/needs", {
    method: "POST",
    body: JSON.stringify({
      need_type: "boat", title: NEED_TITLE, description: "diag", district_id: "jorhat",
      lat: 26.75, lon: 94.22, location_name: "Jorhat test point", urgency: "critical",
      requested_resources: [{ resource_type: "boat", quantity: 1, unit: "units" }],
      reporter_id: "cdp-trace",
    }),
  });
  await api("/api/session/org", {
    method: "POST", body: JSON.stringify({ org_id: "org_demo" }),
  });
  await api("/api/my-org/resources", {
    method: "POST", body: JSON.stringify({ resource_type: "boat", quantity: 2, unit: "units", location: "Jorhat" }),
  });
  await api("/api/my-org/teams", { method: "POST", body: JSON.stringify({ name: "Team A" }) });

  const browser = await puppeteer.launch({
    headless: "new",
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  // Enable CDP network domain and record lifecycle events per requestId
  const cdp = await page.target().createCDPSession();
  await cdp.send("Network.enable");
  const events = {};
  const lines = [];
  const push = (id, ev) => {
    events[id] = events[id] || {};
    events[id][ev] = Date.now();
  };
  cdp.on("Network.requestWillBeSent", (p) => {
    if (!p.request.url.includes("/api/")) return;
    push(p.requestId, "requestWillBeSent");
    events[p.requestId].url = p.request.url.replace(BASE, "");
    events[p.requestId].method = p.request.method;
  });
  cdp.on("Network.requestWillBeSentExtraInfo", (p) => {
    if (events[p.requestId]) push(p.requestId, "extraInfo");
  });
  cdp.on("Network.responseReceived", (p) => {
    if (!events[p.requestId]) return;
    push(p.requestId, "responseReceived");
    events[p.requestId].status = p.response.status;
    events[p.requestId].timing = p.response.timing;
    events[p.requestId].remotePort = p.response.remoteIPAddress
      ? `${p.response.remoteIPAddress}:${p.response.remotePort}`
      : "unknown";
  });
  cdp.on("Network.loadingFinished", (p) => {
    if (events[p.requestId]) push(p.requestId, "loadingFinished");
  });
  cdp.on("Network.loadingFailed", (p) => {
    if (events[p.requestId]) push(p.requestId, "loadingFailed:" + p.errorText);
  });

  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("button", { timeout: 30000 });
  await new Promise((r) => setTimeout(r, 4000));

  // Switch to My Org, then AI tab (same scoped logic as verify script)
  await page.evaluate(() => {
    [...document.querySelectorAll("button")].find((b) => /my org/i.test(b.innerText))?.click();
  });
  await new Promise((r) => setTimeout(r, 2000));
  await page.evaluate(() => {
    const overview = [...document.querySelectorAll("button")].find(
      (b) => b.innerText.trim().toLowerCase() === "overview"
    );
    [...overview.parentElement.querySelectorAll("button")].find(
      (b) => b.innerText.trim().toLowerCase() === "ai"
    )?.click();
  });
  await new Promise((r) => setTimeout(r, 2000));
  const needClicked = await page.evaluate((title) => {
    const panels = [...document.querySelectorAll("div")]
      .filter((d) => d.innerText && d.innerText.includes("QUICK ANALYSIS"))
      .filter((d) => d.querySelector("button"))
      .sort((a, b) => a.innerText.length - b.innerText.length);
    const panel = panels[0];
    if (!panel) return false;
    const btn = [...panel.querySelectorAll("button")].find((b) => b.innerText.includes(title));
    if (!btn) return false;
    btn.click();
    return true;
  }, NEED_TITLE);

  // Wait up to 40s for analyze-need loadingFinished in CDP events
  let evKey = null;
  for (let i = 0; i < 200; i++) {
    evKey = Object.keys(events).find(
      (k) => events[k].url && events[k].url.includes("analyze-need") && events[k].loadingFinished
    );
    if (evKey) break;
    evKey = Object.keys(events).find(
      (k) => events[k].url && events[k].url.includes("analyze-need")
    );
    if (evKey && events[evKey].loadingFinished) break;
    await new Promise((r) => setTimeout(r, 200));
  }

  await new Promise((r) => setTimeout(r, 1000));

  // Report only the interesting requests (analyze-need + heavy layers)
  const interesting = Object.entries(events)
    .filter(([k, e]) => e.url && (e.url.includes("analyze-need") || e.url.includes("flood") || e.url.includes("needs?") || e.url.includes("offers")))
    .map(([k, e]) => {
      const t = (name) => e[name] || null;
      const rel = (a, b) => (e[a] && e[b] ? e[b] - e[a] : null);
      return {
        url: e.url,
        method: e.method,
        status: e.status,
        sendToResponseMs: rel("requestWillBeSent", "responseReceived"),
        responseToLoadedMs: rel("responseReceived", "loadingFinished"),
        timing: e.timing ? {
          // Chrome resource timing phases (ms relative to request start)
          proxyStart: e.timing.proxyStart ?? -1,
          proxyEnd: e.timing.proxyEnd ?? -1,
          sendStart: e.timing.sendStart ?? -1,
          sendEnd: e.timing.sendEnd ?? -1,
          receiveHeadersStart: e.timing.receiveHeadersStart ?? -1,
          receiveHeadersEnd: e.timing.receiveHeadersEnd ?? -1,
        } : null,
        remote: e.remotePort,
      };
    });

  console.log(JSON.stringify({ tag: TAG, needClicked, interesting }, null, 2));
  await browser.close();
  process.exit(0);
}

run().catch((e) => { console.error(e); process.exit(1); });
