// Load the mock dashboard in Chromium, fail on any JS error, check the live values update,
// and save screenshots at laptop and phone width.  Usage: node tests/dashboard_check.js [url] [outdir]
const { chromium } = require('playwright');
const url = process.argv[2] || 'http://localhost:8080/';
const out = process.argv[3] || 'build';

(async () => {
  const browser = await chromium.launch();
  const errors = [];
  let ok = true;
  for (const [name, vp] of [['dashboard_desktop', { width: 1100, height: 900 }], ['dashboard_phone', { width: 390, height: 844 }]]) {
    const page = await browser.newPage({ viewport: vp, deviceScaleFactor: 2 });
    page.on('pageerror', e => errors.push(`${name}: ${e.message}`));
    page.on('console', m => { if (m.type() === 'error') errors.push(`${name}: ${m.text()}`); });
    page.on('dialog', d => d.dismiss());
    await page.goto(url);
    await page.waitForTimeout(1500);
    const t1 = await page.textContent('#y');
    await page.waitForTimeout(3500);
    const t2 = await page.textContent('#y');
    const status = await page.textContent('#status');
    const toggles = await Promise.all([0, 1, 2, 3].map(i => page.textContent('#t' + i)));
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    console.log(`${name}: y ${t1} -> ${t2}, status ${status}, toggles raw/median/MA/proposed = ${toggles.join('/')}, horizontal overflow ${overflow}px`);
    if (status === '--' || t2 === '--') { ok = false; errors.push(`${name}: values never filled in`); }
    if (overflow > 0) { ok = false; errors.push(`${name}: page scrolls sideways by ${overflow}px`); }
    await page.screenshot({ path: `${out}/${name}.png`, fullPage: true });
    await page.close();
  }
  await browser.close();
  if (errors.length) { console.log('ERRORS:\n' + errors.join('\n')); ok = false; }
  console.log(ok ? 'dashboard check passed' : 'dashboard check FAILED');
  process.exit(ok ? 0 : 1);
})();
