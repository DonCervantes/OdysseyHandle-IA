import {chromium} from 'playwright';
import {execFileSync} from 'node:child_process';
import path from 'node:path';
import fs from 'node:fs';
const root=path.dirname(execFileSync('git',['rev-parse','--path-format=absolute','--git-common-dir'],{encoding:'utf8'}).trim());
const executablePath=process.env.CHROME_PATH||'/Users/dylanmartinezcastillo/Library/Caches/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-mac-arm64/chrome-headless-shell';
const browser=await chromium.launch({headless:true,executablePath});
for (const [name,url] of [['front','http://localhost:5173/app/parches'],['dash','http://localhost:8501']]) {
 const page=await browser.newPage({viewport:{width:1920,height:1080}});await page.goto(url);await page.waitForTimeout(5000);console.log(name,(await page.locator('body').innerText()).slice(0,6500));await page.screenshot({path:path.join(root,'var/video',name+'.png')});await page.close();
}
await browser.close();
