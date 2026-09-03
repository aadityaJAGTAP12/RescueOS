const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

const OUTPUT_DIR = 'D:\\tmp\\chrome-output';
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

(async () => {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
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
  
  console.log('Navigating to http://localhost:3000/ ...');
  await page.goto('http://localhost:3000/', { 
    waitUntil: 'networkidle2',
    timeout: 30000 
  });
  
  console.log('Waiting 12s for map layers to load...');
  await new Promise(r => setTimeout(r, 12000));
  
  await page.screenshot({ path: path.join(OUTPUT_DIR, 'full.png'), fullPage: false });
  console.log('Screenshot saved.');
  
  const results = await page.evaluate(() => {
    const data = {};
    
    const mapEl = document.querySelector('.leaflet-container');
    data.hasLeafletMap = !!mapEl;
    data.mapSize = mapEl ? { w: mapEl.offsetWidth, h: mapEl.offsetHeight } : null;
    
    // SVG paths in overlay pane
    data.svgPaths = document.querySelectorAll('.leaflet-overlay-pane path').length;
    data.svgPolygons = document.querySelectorAll('.leaflet-overlay-pane polygon').length;
    data.svgLines = document.querySelectorAll('.leaflet-overlay-pane line').length;
    data.svgCircles = document.querySelectorAll('.leaflet-overlay-pane circle').length;
    
    // Canvas
    data.canvasElements = document.querySelectorAll('canvas').length;
    
    // Tiles
    data.tileImages = document.querySelectorAll('.leaflet-tile-pane img').length;
    
    // Markers
    data.markers = document.querySelectorAll('.leaflet-marker-pane *').length;
    data.markerIcons = document.querySelectorAll('.leaflet-marker-icon').length;
    
    // Popups
    data.popups = document.querySelectorAll('.leaflet-popup').length;
    
    // Checkboxes (layer toggles)
    data.checkboxes = document.querySelectorAll('input[type="checkbox"]').length;
    
    // Overlay pane children
    const overlayPane = document.querySelector('.leaflet-overlay-pane');
    data.overlayChildren = overlayPane ? overlayPane.children.length : 0;
    data.overlayHTML = overlayPane ? overlayPane.innerHTML.substring(0, 1000) : 'no overlay pane';
    
    // All text content
    const allText = document.body.innerText;
    data.bodyTextLength = allText.length;
    data.bodyTextSample = allText.substring(0, 4000);
    
    // Specific checks
    data.hasReliefOSTitle = allText.includes('RELIEFOS');
    data.hasFloodLayer = allText.includes('Flood');
    data.hasRoadLayer = allText.includes('Road');
    data.hasBridgeLayer = allText.includes('Bridge');
    data.hasMedicalLayer = allText.includes('Medical') || allText.includes('medical');
    data.hasNeedsLayer = allText.includes('Need');
    data.hasDistricts = allText.includes('Sivasagar') || allText.includes('Jorhat') || allText.includes('Charaideo') || allText.includes('Golaghat');
    data.hasAIPanel = allText.includes('AI') || allText.includes('Coordinator');
    data.hasActivityBar = allText.includes('WHAT CHANGED') || allText.includes('FLOOD');
    data.hasSearchBar = allText.includes('SEARCH') || allText.includes('⌘K');
    
    // LayerRail sections
    const layerLabels = [];
    document.querySelectorAll('[class*="layer"], [class*="Layer"]').forEach(el => {
      if (el.textContent.trim()) layerLabels.push(el.textContent.trim().substring(0, 100));
    });
    data.layerLabels = layerLabels.slice(0, 20);
    
    return data;
  });
  
  console.log('\n=== RENDERED STATE ===');
  console.log(JSON.stringify(results, null, 2));
  
  console.log('\n=== CONSOLE ERRORS ===');
  const errors = consoleMsgs.filter(m => m.type === 'error');
  console.log(`Total: ${errors.length}`);
  errors.forEach(e => console.log(`  ERROR: ${e.text.substring(0, 200)}`));
  
  console.log('\n=== PAGE ERRORS ===');
  console.log(`Total: ${pageErrors.length}`);
  pageErrors.forEach(e => console.log(`  ERROR: ${e.substring(0, 200)}`));
  
  console.log('\n=== WARNINGS ===');
  const warnings = consoleMsgs.filter(m => m.type === 'warning');
  console.log(`Total: ${warnings.length}`);
  warnings.slice(0, 5).forEach(w => console.log(`  WARN: ${w.text.substring(0, 200)}`));
  
  console.log('\n=== ALL CONSOLE MESSAGES ===');
  consoleMsgs.forEach(m => console.log(`  [${m.type}] ${m.text.substring(0, 150)}`));
  
  await browser.close();
})().catch(err => {
  console.error('Script failed:', err.message);
  process.exit(1);
});
