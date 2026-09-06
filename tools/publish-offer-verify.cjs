const puppeteer = require("puppeteer");

const BASE = "http://localhost:3000";
const API = "http://localhost:5001";
const TAG = `diag-${Date.now()}`;
const NEED_TITLE = `Verify boat evacuation ${TAG}`;

async function api(path, options = {}) {
  const resp = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const body = await resp.json().catch(() => ({}));
  return { status: resp.status, body };
}

async function run() {
  // ------------------------------------------------------------------
  // 1. Seed: org, one OPEN boat need, private inventory (2 boats + team)
  // ------------------------------------------------------------------
  await api("/api/organizations", {
    method: "POST",
    body: JSON.stringify({
      id: "org_demo",
      name: "Demo Relief Org",
      organization_type: "ngo",
      description: "Publish-offer verification org",
    }),
  });
  const needResp = await api("/api/needs", {
    method: "POST",
    body: JSON.stringify({
      need_type: "boat",
      title: NEED_TITLE,
      description: "Seeded by publish-offer verification",
      district_id: "jorhat",
      lat: 26.75,
      lon: 94.22,
      location_name: "Jorhat test point",
      urgency: "critical",
      requested_resources: [{ resource_type: "boat", quantity: 1, unit: "units" }],
      reporter_id: "publish-offer-verify",
    }),
  });
  const resource = await api("/api/orgs/org_demo/resources", {
    method: "POST",
    body: JSON.stringify({ resource_type: "boat", quantity: 2, unit: "units", location: "Jorhat" }),
  });
  const team = await api("/api/orgs/org_demo/teams", {
    method: "POST",
    body: JSON.stringify({ name: "Rescue Team A" }),
  });

  const before = await api("/api/offers?organization_id=org_demo");
  const beforeCount = before.body.offers?.length ?? null;

  // ------------------------------------------------------------------
  // 2. Browser pass with full network capture
  // ------------------------------------------------------------------
  const browser = await puppeteer.launch({
    headless: "new",
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  const traffic = [];
  page.on("request", (req) => {
    const url = req.url();
    if (url.includes("/api/")) {
      traffic.push({
        phase: "request",
        method: req.method(),
        url: url.replace(API, "").replace(BASE, ""),
        postData: req.postData() ? req.postData().slice(0, 400) : null,
        t: Date.now(),
      });
    }
  });
  page.on("response", async (res) => {
    const url = res.url();
    if (url.includes("/api/")) {
      let body = null;
      try { body = JSON.stringify(await res.json()); } catch {}
      traffic.push({
        phase: "response",
        status: res.status(),
        url: url.replace(API, "").replace(BASE, ""),
        body: body ? body.slice(0, 1200) : null,
        t: Date.now(),
      });
    }
  });
  const consoleErrors = [];
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
  page.on("pageerror", (e) => consoleErrors.push(`PAGEERROR: ${e.message}`));

  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("button", { timeout: 30000 });
  await new Promise((r) => setTimeout(r, 4000));

  // Poll helper: wait until evaluate() predicate returns truthy
  async function waitForEval(fn, timeoutMs, pollMs = 200) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const v = await page.evaluate(fn);
      if (v) return v;
      await new Promise((r) => setTimeout(r, pollMs));
    }
    return null;
  }

  // 2a. Switch to MY ORGANIZATION workspace (waits for workspace render)
  const switched = await page.evaluate(() => {
    const btn = [...document.querySelectorAll("button")].find((b) => /my org/i.test(b.innerText));
    if (btn) { btn.click(); return true; }
    return false;
  });
  const orgReady = await waitForEval(
    () => document.body.innerText.includes("My Organization") &&
          document.body.innerText.includes("Overview"),
    10000
  );

  // 2b. Open the AI tab (tab bar button, NOT the header "AI" toggle)
  const aiTab = await page.evaluate(() => {
    const btns = [...document.querySelectorAll("button")].filter(
      (b) => b.innerText.trim().toLowerCase() === "ai"
    );
    const btn = btns[btns.length - 1]; // last match = workspace tab bar
    if (btn) { btn.click(); return btns.length; }
    return 0;
  });
  // Wait for the AI panel to actually render its need buttons
  const aiReady = await waitForEval(
    () => {
      const panels = [...document.querySelectorAll("div")]
        .filter((d) => d.innerText && d.innerText.includes("QUICK ANALYSIS"))
        .filter((d) => d.querySelector("button"))
        .sort((a, b) => a.innerText.length - b.innerText.length);
      return panels.length > 0 ? { found: true } : null;
    },
    15000
  );
  await page.screenshot({ path: "/tmp/step2-aitab.png" });

  // 2c. Click a need inside the QUICK ANALYSIS panel (scoped, avoids
  // bottom activity bar / dossier matches). Prefer our seeded need; any
  // boat-type need works since inventory is boats.
  const needClicked = await page.evaluate((title) => {
    const panels = [...document.querySelectorAll("div")]
      .filter((d) => d.innerText && d.innerText.includes("QUICK ANALYSIS"))
      .filter((d) => d.querySelector("button"))
      .sort((a, b) => a.innerText.length - b.innerText.length);
    const panel = panels[0];
    if (!panel) return { found: false };
    const btns = [...panel.querySelectorAll("button")];
    const exact = btns.find((b) => b.innerText.includes(title));
    const boat = btns.find((b) => b.innerText.toLowerCase().includes("boat"));
    const target = exact || boat || btns[0];
    if (!target) return { found: false, btnCount: btns.length };
    target.click();
    return { found: true, used: exact ? "title" : boat ? "boat" : "first" };
  }, NEED_TITLE);

  // Wait for analyze-need response (max 15s)
  let analyzeResp = null;
  for (let i = 0; i < 75; i++) {
    analyzeResp = traffic.find(
      (t) => t.phase === "response" && t.url.includes("/agent/analyze-need")
    );
    if (analyzeResp) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  const analyzeReq = traffic.find((t) => t.phase === "request" && t.url.includes("/agent/analyze-need"));
  await new Promise((r) => setTimeout(r, 500));
  await page.screenshot({ path: "/tmp/step3-analyzed.png" });
  // Wait for the analysis card with its PUBLISH OFFER button to render
  const publishVisible = await waitForEval(
    () => {
      const btn = [...document.querySelectorAll("button")].find(
        (b) => /publish offer/i.test(b.innerText)
      );
      return btn ? { visible: true } : null;
    },
    15000
  );
  const afterNeedClick = await page.evaluate(() => ({
    hasAnalyzing: document.body.innerText.includes("Analyzing..."),
    hasPublish: /publish offer/i.test(document.body.innerText),
    bodySample: document.body.innerText.slice(0, 1200),
  }));

  // 2d. Click PUBLISH OFFER
  const publishClicked = await page.evaluate(() => {
    const btn = [...document.querySelectorAll("button")].find(
      (b) => /publish offer/i.test(b.innerText) && !b.disabled
    );
    if (btn) { btn.click(); return true; }
    return false;
  });

  // Wait for the publish-offer RESPONSE (max 20s) — the fix from last run
  let publishResp = null;
  for (let i = 0; i < 100; i++) {
    publishResp = traffic.find(
      (t) => t.phase === "response" && t.url.includes("/publish-offer")
    );
    if (publishResp) break;
    await new Promise((r) => setTimeout(r, 200));
  }

  // ------------------------------------------------------------------
  // 3. AFTER: authoritative server-side offer count
  // ------------------------------------------------------------------
  const after = await api("/api/offers?organization_id=org_demo");
  const afterCount = after.body.offers?.length ?? null;
  const newest = (after.body.offers || [])
    .slice()
    .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))[0] || null;

  const publishReq = traffic.find((t) => t.phase === "request" && t.url.includes("/publish-offer"));

  console.log(JSON.stringify({
    tag: TAG,
    seed: {
      need: needResp.status,
      resource: resource.status,
      team: team.status,
    },
    beforeCount,
    afterCount,
    delta: afterCount !== null && beforeCount !== null ? afterCount - beforeCount : null,
    ui: { switched, orgReady, aiTab, aiReady, needClicked, publishVisible, afterNeedClick, publishClicked },
    apiTraffic: traffic
      .filter((t) => t.method !== "GET")
      .map((t) => `${t.phase} ${t.status ?? t.method} ${t.url}`),
    publishRequest: publishReq || null,
    publishResponse: publishResp || null,
    analyzeRequest: analyzeReq || null,
    analyzeResponse: analyzeResp
      ? { status: analyzeResp.status, body: analyzeResp.body?.slice(0, 500) }
      : null,
    newestOffer: newest,
    consoleErrors,
  }, null, 2));

  await browser.close();

  const ok =
    publishResp && publishResp.status === 201 && afterCount === (beforeCount ?? 0) + 1;
  if (!ok) process.exit(2);
}

run().catch((err) => {
  console.error("VERIFY_SCRIPT_ERROR", err);
  process.exit(1);
});
