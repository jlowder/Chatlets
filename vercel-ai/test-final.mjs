import { chromium } from 'playwright';
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 400, height: 600 } });
await page.goto('http://localhost:4000');
await page.waitForTimeout(2000);

// Send multiple messages
for (let i = 0; i < 5; i++) {
  const textarea = page.locator('textarea');
  await textarea.fill(`message ${i+1}`);
  await page.keyboard.press('Enter');
  await page.waitForTimeout(3000);
}

await page.screenshot({ path: '/tmp/chat-final.png' });
await browser.close();
