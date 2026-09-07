const puppeteer = require("puppeteer");

const BASE = "http://localhost:3000";

async function api(path, options = {}) {
  const resp = await fetch(`http://localhost:5001${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const body = await resp.json().catch(() => ({}));
  return { status: resp.status, body };
}

async function seed() {
  // Ensure the default org exists, then select it via the identity seam.
  // Org context is now session-derived (reliefos_org_id cookie) — no
  // hardcoded org id is trusted anywhere.
  await api("/api/organizations", {
    method: "POST",
    body: JSON.stringify({
      id: "org_demo",
      name: "Demo Relief Org",
      organization_type: "ngo",
      description: "Browser diagnostic organization",
    }),
  });
  await api("/api/session/org", {
    method: "POST",
    body: JSON.stringify({ org_id: "org_demo" }),
  });

  const needs = [
    ["critical", "OPEN", "boat", "Critical boat evacuation", 26.75, 94.22],
    ["high", "OPEN", "food", "High food supply", 26.77, 94.24],
    ["medium", "RESPONDING", "water", "Medium water response", 26.79, 94.26],
    ["low", "RESOLVED", "shelter", "Low shelter resolved", 26.81, 94.28],
  ];
  for (const [urgency, status, need_type, title, lat, lon] of needs) {
    const created = await api("/api/needs", {
      method: "POST",
      body: JSON.stringify({
        need_type,
        title: `${title} ${Date.now()}`,
        description: "Seeded by UI diagnostics",
        district_id: "jorhat",
        lat,
        lon,
        location_name: "Jorhat test point",
        urgency,
        requested_resources: [{ resource_type: need_type, quantity: 1, unit: "units" }],
        reporter_id: "ui-diagnostics",
      }),
    });
    if (status !== "OPEN" && created.body.need?.id) {
      await api(`/api/needs/${created.body.need.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status, actor: "ui-diagnostics" }),
      });
    }
  }
}

async function uiSnapshot(page) {
  return page.evaluate(() => {
    const text = document.body.innerText;
    const overlay = [...document.querySelectorAll("div")]
      .map((el) => el.innerText || "")
      .find((t) => /\d+ settlements .* \d+ needs .* \d+ ops .* \d+ offers/.test(t));
    return {
      overlay,
      markerIcons: document.querySelectorAll(".leaflet-marker-icon").length,
      needButtons: [...document.querySelectorAll("button")].filter((b) =>
        ["critical", "high", "medium", "low", "open", "responding", "resolved"].includes(
          b.innerText.trim().toLowerCase()
        )
      ).map((b) => b.innerText.trim()),
      hasPublishOffer: text.includes("Publish Offer") || text.includes("PUBLISH OFFER"),
    };
  });
}

async function clickButton(page, label) {
  await page.$$eval("button", (buttons, text) => {
    const b = buttons.find((button) => button.innerText.trim().toLowerCase() === text);
    if (b) b.click();
  }, label.toLowerCase());
  await new Promise((r) => setTimeout(r, 1200));
}

async function run() {
  await seed();
  const browser = await puppeteer.launch({
    headless: "new",
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
  });
  const page = await browser.newPage();
  const requests = [];
  const responses = [];
  const consoleErrors = [];
  page.on("request", (req) => {
    const url = req.url();
    if (url.includes("/api/")) requests.push({ method: req.method(), url });
  });
  page.on("response", (res) => {
    const url = res.url();
    if (url.includes("/api/")) responses.push({ status: res.status(), url });
  });
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });

  await page.setViewport({ width: 1440, height: 900 });
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await new Promise((r) => setTimeout(r, 4000));

  const before = await uiSnapshot(page);
  const urgencySnapshots = {};
  for (const urgency of ["critical", "high", "medium", "low"]) {
    await clickButton(page, "All Urgency");
    await clickButton(page, urgency);
    urgencySnapshots[urgency] = await uiSnapshot(page);
  }
  await clickButton(page, "All Urgency");
  const statusSnapshots = {};
  for (const status of ["open", "responding", "resolved"]) {
    if (statusSnapshots.previousStatus) {
      await clickButton(page, statusSnapshots.previousStatus);
    }
    await clickButton(page, status);
    statusSnapshots[status] = await uiSnapshot(page);
    statusSnapshots.previousStatus = status;
  }
  delete statusSnapshots.previousStatus;

  const offerBefore = await api("/api/offers?organization_id=org_demo");
  await page.$$eval("button", (buttons) => {
    const b = buttons.find((button) => button.innerText.includes("+ Offer"));
    if (b) b.click();
  });
  await new Promise((r) => setTimeout(r, 500));
  await page.type("input[placeholder='e.g., Jorhat Relief Camp']", "Diagnostic offer");
  await page.type("input[placeholder='26.74']", "26.75");
  await page.type("input[placeholder='94.21']", "94.22");
  await page.$$eval("button", (buttons) => {
    const b = buttons.find((button) => button.innerText.trim() === "Publish Offer");
    if (b) b.click();
  });
  await new Promise((r) => setTimeout(r, 1200));
  const offerAfter = await api("/api/offers?organization_id=org_demo");

  console.log(JSON.stringify({
    before,
    urgencySnapshots,
    statusSnapshots,
    offerBeforeCount: offerBefore.body.offers?.length ?? null,
    offerAfterCount: offerAfter.body.offers?.length ?? null,
    apiRequests: requests.filter((r) => /needs|offers|publish-offer/.test(r.url)),
    apiResponses: responses.filter((r) => /needs|offers|publish-offer/.test(r.url)),
    consoleErrors,
  }, null, 2));

  await browser.close();
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
