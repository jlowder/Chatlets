import { chromium } from 'playwright';
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto('http://localhost:4000');
await page.waitForTimeout(2000);

const textarea = page.locator('textarea');
await textarea.click();
await textarea.fill('say a very long message that will definitely make the chat content overflow the viewport and require scrolling so we can verify the auto-scroll works correctly');
await page.keyboard.press('Enter');

// Wait for the LLM response
await page.waitForTimeout(10000);

const scrollInfo = await page.evaluate(() => {
  const container = document.querySelector('[class*="overflow-y-auto"]');
  if (!container) return { found: false };
  return {
    scrollHeight: container.scrollHeight,
    clientHeight: container.clientHeight,
    scrollTop: container.scrollTop,
    overflowY: window.getComputedStyle(container).overflowY,
    contentOverflows: container.scrollHeight > container.clientHeight,
  };
});
console.log('Scroll info:', JSON.stringify(scrollInfo));

await page.screenshot({ path: '/tmp/chat-response2.png' });
await browser.close();
