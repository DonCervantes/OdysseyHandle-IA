import {fileURLToPath} from 'node:url';
// Prefer an explicit browser, then an existing local installation; install only when absent.
import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
import {execFileSync} from 'node:child_process';import {chromium} from 'playwright';
export function browserPath(){
 if(process.env.CHROME_PATH)return process.env.CHROME_PATH;
 const expected=chromium.executablePath();if(fs.existsSync(expected))return expected;
 const base=path.join(os.homedir(),'Library/Caches/ms-playwright');
 if(fs.existsSync(base))for(const p of fs.readdirSync(base).filter(p=>p.startsWith('chromium_headless_shell-')).sort().reverse()){
  const f=path.join(base,p,'chrome-headless-shell-mac-arm64/chrome-headless-shell');if(fs.existsSync(f))return f;
 }
 execFileSync(process.execPath,[path.join(path.dirname(fileURLToPath(import.meta.url)),'node_modules/playwright/cli.js'),'install','chromium'],{stdio:'inherit'});
 if(!fs.existsSync(expected))throw new Error('Chromium no instalado; definir CHROME_PATH.');return expected;
}
