const { chromium } = require(process.env.PLAYWRIGHT_MODULE);
const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.BROWSER_EXECUTABLE});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', message => {
    if (message.type() === 'error' && /content security policy|violates.*directive/i.test(message.text())) errors.push(message.text());
  });
  try {
    const response = await page.goto(process.env.BASE_URL || 'http://127.0.0.1:8765');
    assert.equal(response.status(), 200);
    await page.getByRole('heading', {name: 'Tổng quan', exact: true}).waitFor();
    await page.getByText('Lịch sử bắt đầu từ dữ liệu thật', {exact: true}).waitFor();
    await page.screenshot({path: 'artifacts/ui-desktop.png', fullPage: true});
    await page.getByRole('button', {name: /Phân tích premium/}).click();
    await page.getByText('Median sản phẩm trong kỳ').waitFor();
    await page.getByRole('button', {name: /Mô phỏng lịch sử/}).click();
    await page.getByRole('button', {name: 'Xem kết quả mô phỏng →'}).click();
    await page.getByRole('alert').filter({hasText: 'missing:'}).waitFor();
    await page.getByRole('button', {name: /Phòng kịch bản/}).click();
    await page.getByLabel('Giá mua ask (VND/lượng)').fill('140000000');
    await page.getByLabel('Thế giới quy đổi hiện tại (VND/lượng)').fill('120000000');
    await page.getByLabel('Spread tương lai (VND/lượng)').fill('3000000');
    await page.getByRole('button', {name: 'Xem kết quả mô phỏng →'}).click();
    await page.getByText('−11.000.000 ₫', {exact: true}).first().waitFor();
    assert.equal(await page.locator('canvas').count(), 1);
    assert.ok(await page.getByText('SCENARIO, NOT OBSERVED PRICE', {exact: false}).count());
    await page.getByRole('button', {name: /Dữ liệu & nguồn/}).click();
    await page.getByRole('heading', {name: 'Tình trạng nguồn dữ liệu'}).waitFor();
    await page.setViewportSize({width: 390, height: 844});
    await page.getByRole('button', {name: /Tổng quan/}).click();
    await page.screenshot({path: 'artifacts/ui-mobile.png', fullPage: true});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    await page.getByRole('button', {name: /Phòng kịch bản/}).focus();
    await page.keyboard.press('Enter');
    await page.getByRole('heading', {name: 'Phòng kịch bản', exact: true}).waitFor();
    assert.deepEqual(errors, []);
    fs.writeFileSync(process.env.BROWSER_REPORT || 'artifacts/browser-tests.json', JSON.stringify({status: 'passed', checked_at: new Date().toISOString(), base_url: process.env.BASE_URL || 'http://127.0.0.1:8765', checks: ['empty market state', 'five screens', 'missing history rejected', 'server Decimal scenario loss 11m', 'scenario chart', 'mobile no overflow', 'keyboard navigation', 'no runtime JS or CSP errors']}, null, 2));
    console.log('Browser QA: 8 checks passed (desktop 1440px, mobile 390px).');
  } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode = 1;});
