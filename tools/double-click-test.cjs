// TEMPORARY diagnostic (NOT production code): rapid double-click Publish Offer
// test — confirms only one POST /publish-offer fires and only one offer row is
// created when the button is clicked twice in quick succession.
const puppeteer = require("puppeteer");

const BASE = "http://localhost:3000";
const API = "http://localhost:5001";
const TAG = `dbl-${Date.now()}`;
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
      reporter_id: "double-click-test",
    }),
  });
  await api("/api/orgs/org_demo/resources", {
    method: "POST", body: JSON.stringify({ resource_type: "boat", quantity: 2, unit: "units", location: "Jorhat" }),
  });
  await api("/api/orgs/org_demo/teams", { method: "POST", body: JSON.stringify({ name: "Team A" }) });

  const before = await api("/api/offers?organization_id=org_demo");
  const beforeCount = before.body.offers?.length ?? 0;

  const browser = await puppeteer.launch({
    headless: "new",
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  await page.evaluateOnNewDocument(() => {
    window.__publishPosts = 0;
    const orig = window.fetch;
    window.fetch = (...args) => {
      if (String(args[0]).includes("/publish-offer")) window.__publishPosts += 1;
      return orig(...args);
    };
  });

  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("button", { timeout: 30000 });
  await new Promise((r) => setTimeout(r, 4000));

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
  // Wait for QUICK ANALYSIS buttons
  for (let i = 0; i < 50; i++) {
    const ok = await page.evaluate(() => {
      const panels = [...document.querySelectorAll("div")]
        .filter((d) => d.innerText && d.innerText.includes("QUICK ANALYSIS"))
        .filter((d) => d.querySelector("button"))
        .sort((a, b) => a.innerText.length - b.innerText.length);
      return panels.length > 0;
    });
    if (ok) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  const clicked = await page.evaluate((title) => {
    const panels = [...document.querySelectorAll("div")]
      .filter((d) => d.innerText && d.innerText.includes("QUICK ANALYSIS"))
      .filter((d) => d.querySelector("button"))
      .sort((a, b) => a.innerText.length - b.innerText.length);
    const btn = [...panels[0].querySelectorAll("button")].find((b) => b.innerText.includes(title));
    if (!btn) return false;
    btn.click();
    return true;
  }, NEED_TITLE);

  // Wait for PUBLISH OFFER button
  for (let i = 0; i < 75; i++) {
    const ok = await page.evaluate(() =>
      [...document.querySelectorAll("button")].some((b) => /publish offer/i.test(b.innerText))
    );
    if (ok) break;
    await new Promise((r) => setTimeout(r, 200));
  }

  // DOUBLE-CLICK: two clicks as fast as the page allows
  const clickResults = await page.evaluate(() => {
    const find = () =>
      [...document.querySelectorAll("button")].find((b) => /publish offer/i.test(b.innerText));
    const first = find();
    if (!first) return { first: false };
    const firstDisabled = first.disabled;
    first.click();
    const second = find();
    const secondDisabled = second ? second.disabled : "gone";
    if (second && !second.disabled) second.click();
    return { first: true, firstDisabled, secondDisabled };
  });

  // Wait for publish POST to complete
  let posts = 0;
  for (let i = 0; i < 100; i++) {
    posts = await page.evaluate(() => window.__publishPosts || 0);
    const done = await page.evaluate(() =>
      [...document.querySelectorAll("button")].some(
        (b) => /publish offer/i.test(b.innerText) && !b.disabled
      ) || document.body.innerText.includes("Offer published")
    );
    if (done && posts >= 1) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  await new Promise((r) => setTimeout(r, 1500));
  posts = await page.evaluate(() => window.__publishPosts || 0);

  const after = await api("/api/offers?organization_id=org_demo");
  const afterCount = after.body.offers?.length ?? 0;

  console.log(JSON.stringify({
    tag: TAG,
    beforeCount,
    afterCount,
    delta: afterCount - beforeCount,
    clickResults,
    publishPostsFired: posts,
  }, null, 2));
  await browser.close();
  process.exit(0);
}

run().catch((e) => { console.error(e); process.exit(1); });
