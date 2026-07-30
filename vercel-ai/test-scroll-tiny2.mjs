import { chromium } from 'playwright';
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 400, height: 600 } });
await page.goto('http://localhost:4000');
await page.waitForTimeout(2000);

// Send multiple messages to build height
const messages = ['message 1', 'message 2', 'message 3', 'message 4', 'message 5'];

for (let i = 0; i < messages.length; i++) {
  const textarea = page.locator('textarea');
  await textarea.fill(messages[i]);
  await page.keyboard.press('Enter');
  
  // Wait for response
  await page.waitForTimeout(3000);
}

// Check scroll position after all messages
const info = await page.evaluate(() => {
  const container = document.querySelector('[class*="overflow-y-auto"]');
  if (!container) return null;
  return {
    scrollHeight: container.scrollHeight,
    clientHeight: container.clientHeight,
    scrollTop: container.scrollTop,
    containerHeight: container.offsetHeight,
    windowInnerHeight: window.innerHeight,
  };
});
console.log('Final scroll info:', JSON.stringify(info, null, 2));

await page.screenshot({ path: '/tmp/chat-tiny-final.png' });
await browser.close();
