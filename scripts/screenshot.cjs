#!/usr/bin/env node
// Full-page screenshot of a real URL:
//   node scripts/screenshot.cjs <url> <out.png> [width] [height]
// Install the browser once with: npx playwright install chromium
const { chromium } = require('playwright');

const [url, out, width = '1440', height = '900'] = process.argv.slice(2);
if (!url || !out) {
  console.error('usage: screenshot.cjs <url> <out.png> [width] [height]');
  process.exit(1);
}

(async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({
      viewport: { width: Number(width), height: Number(height) },
    });
    await page.goto(url, { waitUntil: 'networkidle' });
    await page.waitForTimeout(500); // Let entry animations settle before capture.
    await page.screenshot({ path: out, fullPage: true });
    console.log(out);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
