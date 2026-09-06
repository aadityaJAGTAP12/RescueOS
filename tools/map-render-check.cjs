// TEMPORARY diagnostic (NOT production code): post-fix map render check.
// Loads the app, waits for flood polygons to paint, counts SVG paths and
// marker icons, saves a screenshot to the project root as map-after-fix.png.
const puppeteer = require("puppeteer");

async function run() {
  const browser = await puppeteer.launch({
    headless: "new",
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  await page.goto("http://localhost:3000", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("button", { timeout: 30000 });
  await new Promise((r) => setTimeout(r, 15000));

  const check = await page.evaluate(() => ({
    svgPaths: document.querySelectorAll("path.leaflet-interactive").length,
    markers: document.querySelectorAll(".leaflet-marker-icon").length,
    overlayText:
      ([...document.querySelectorAll("div")]
        .map((el) => el.innerText || "")
        .find((t) => /\d+ settlements .* \d+ needs/.test(t)) || "").slice(0, 120),
  }));
  await page.screenshot({ path: "map-after-fix.png" });
  console.log(JSON.stringify(check, null, 2));
  await browser.close();
}

run().catch((e) => { console.error(e); process.exit(1); });
