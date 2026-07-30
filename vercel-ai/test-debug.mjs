import { chromium } from 'playwright';
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 400, height: 600 } });
await page.goto('http://localhost:4000');
await page.waitForTimeout(2000);

// Send a few messages
for (let i = 0; i < 3; i++) {
  const textarea = page.locator('textarea');
  await textarea.fill(`message ${i+1}`);
  await page.keyboard.press('Enter');
  await page.waitForTimeout(3000);
}

const debug = await page.evaluate(() => {
  const root = document.querySelector('[class*="flex-col"]');
  const chatContainer = document.querySelector('[class*="overflow-y-auto"]');
  
  return {
    root: root ? {
      height: root.offsetHeight,
      display: window.getComputedStyle(root).display,
      flex: window.getComputedStyle(root).flex,
    } : null,
    chatContainer: chatContainer ? {
      height: chatContainer.offsetHeight,
      clientHeight: chatContainer.clientHeight,
      scrollHeight: chatContainer.scrollHeight,
      overflowY: window.getComputedStyle(chatContainer).overflowY,
      display: window.getComputedStyle(chatContainer).display,
      flex: window.getComputedStyle(chatContainer).flex,
      minHeight: window.getComputedStyle(chatContainer).minHeight,
    } : null,
  };
});

console.log('Debug info:', JSON.stringify(debug, null, 2));
await browser.close();
