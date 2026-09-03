const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

const OUTPUT_DIR = 'D:\\tmp\\chrome-output';
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

(async () => {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
  });
  
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080 });
  
  const consoleMsgs = [];
  page.on('console', msg => {
    consoleMsgs.push({ type: msg.type(), text: msg.text() });
  });
  
  const pageErrors = [];
  page.on('pageerror', err => {
    pageErrors.push(err.message);
  });
  
  console.log('Navigating...');
  try {
    await page.goto('http://localhost:3000/', { 
      waitUntil: 'domcontentloaded',
      timeout: 15000 
    });
    console.log('Page loaded, waiting 15s for React + map...');
    await new Promise(r => setTimeout(r, 15000));
  } catch(e) {
    console.log('Navigation error:', e.message);
    // Try to continue anyway
  }
  
  await page.screenshot({ path: path.join(OUTPUT_DIR, 'full.png'), fullPage: false });
  console.log('Screenshot saved.');
  
  const results = await page.evaluate(() => {
    const data = {};
    
    const mapEl = document.querySelector('.leaflet-container');
    data.hasLeafletMap = !!mapEl;
    data.mapSize = mapEl ? { w: mapEl.offsetWidth, h: mapEl.offsetHeight } : null;
    data.svgPaths = document.querySelectorAll('.leaflet-overlay-pane path').length;
    data.svgPolygons = document.querySelectorAll('.leaflet-overlay-pane polygon').length;
    data.svgLines = document.querySelectorAll('.leaflet-overlay-pane line').length;
    data.svgCircles = document.querySelectorAll('.leaflet-overlay-pane circle').length;
    data.canvasElements = document.querySelectorAll('canvas').length;
    data.tileImages = document.querySelectorAll('.leaflet-tile-pane img').length;
    data.markers = document.querySelectorAll('.leaflet-marker-pane *').length;
    data.markerIcons = document.querySelectorAll('.leaflet-marker-icon').length;
    data.popups = document.querySelectorAll('.leaflet-popup').length;
    data.checkboxes = document.querySelectorAll('input[type="checkbox"]').length;
    
    const overlayPane = document.querySelector('.leaflet-overlay-pane');
    data.overlayChildren = overlayPane ? overlayPane.children.length : 0;
    
    const allText = document.body.innerText;
    data.bodyTextLength = allText.length;
    data.bodyTextSample = allText.substring(0, 4000);
    
    data.hasReliefOSTitle = allText.includes('RELIEFOS');
    data.hasFloodLayer = allText.includes('Flood');
    data.hasRoadLayer = allText.includes('Road');
    data.hasBridgeLayer = allText.includes('Bridge');
    data.hasMedicalLayer = allText.includes('Medical');
    data.hasDistricts = allText.includes('Sivasagar') || allText.includes('Jorhat') || allText.includes('Charaideo') || allText.includes('Golaghat');
    data.hasAIPanel = allText.includes('AI');
    data.hasActivityBar = allText.includes('WHAT CHANGED') || allText.includes('FLOOD');
    data.hasSearchBar = allText.includes('SEARCH') || allText.includes('⌘K');
    
    return data;
  });
  
  console.log('\n=== RENDERED STATE ===');
  console.log(JSON.stringify(results, null, 2));
  
  console.log('\n=== PAGE ERRORS ===');
  console.log(`Total: ${pageErrors.length}`);
  pageErrors.forEach(e => console.log(`  ERROR: ${e.substring(0, 300)}`));
  
  console.log('\n=== CONSOLE ERRORS ===');
  const errors = consoleMsgs.filter(m => m.type === 'error');
  console.log(`Total: ${errors.length}`);
  errors.forEach(e => console.log(`  ERROR: ${e.text.substring(0, 300)}`));
  
  console.log('\n=== ALL CONSOLE ===');
  consoleMsgs.forEach(m => console.log(`  [${m.type}] ${m.text.substring(0, 200)}`));
  
  await browser.close();
})().catch(err => {
  console.error('Script failed:', err.message);
  process.exit(1);
});
