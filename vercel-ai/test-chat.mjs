import { chromium } from 'playwright';
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto('http://localhost:4000');
await page.waitForTimeout(2000);
await page.screenshot({ path: '/tmp/chat-init.png' });

const textarea = page.locator('textarea');
await textarea.click();
await textarea.fill('hello world');
await page.keyboard.press('Enter');

await page.waitForTimeout(8000);
await page.screenshot({ path: '/tmp/chat-response.png' });

// Also log scroll info
const scrollInfo = await page.evaluate(() => {
  const container = document.querySelector('[class*="overflow-y-auto"]');
  if (!container) return { found: false };
  return {
    found: true,
    scrollHeight: container.scrollHeight,
    clientHeight: container.clientHeight,
    scrollTop: container.scrollTop,
    overflowY: window.getComputedStyle(container).overflowY,
  };
});
console.log('Scroll info:', JSON.stringify(scrollInfo));

await browser.close();
