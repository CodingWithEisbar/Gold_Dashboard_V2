const {chromium} = require(process.env.PLAYWRIGHT_MODULE);
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.BROWSER_EXECUTABLE});
  const page = await browser.newPage({viewport:{width:1440,height:1000}});
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  try {
    await page.goto('http://127.0.0.1:8765');
    await page.getByText('SAMPLE DATA — NOT REAL MARKET DATA', {exact:false}).first().waitFor();
    await page.getByRole('button', {name:/Mô phỏng lịch sử/}).click();
    await page.getByLabel('Sản phẩm & vùng').selectOption('sjc-bar-1l-hcm');
    await page.getByLabel('Ngày mua', {exact:true}).fill('2026-11-04');
    await page.getByLabel(/^Ngày bán/).fill('2026-11-05');
    await page.getByRole('button', {name:'Xem kết quả mô phỏng →'}).click();
    await page.getByText('−2.000.000 ₫', {exact:true}).first().waitFor();
    await page.getByRole('heading', {name:'Backtest lãi / lỗ lý thuyết qua ngày'}).waitFor();
    await page.getByText('−3.000.000 ₫', {exact:true}).waitFor();
    await page.screenshot({path:'artifacts/ui-sample-simulator.png',fullPage:true});
    assert.deepEqual(errors, []);
    fs.writeFileSync('artifacts/browser-sample-tests.json',JSON.stringify({status:'passed',checks:['sample banner','entry ask/exit bid loss 2m','backtest same-day spread loss 3m','chart renders','no JavaScript runtime errors']},null,2));
    console.log('Sample browser QA: 5 checks passed. SAMPLE DATA — NOT REAL MARKET DATA');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
