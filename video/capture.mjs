import {chromium} from 'playwright';
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
const root=path.dirname(execFileSync('git',['rev-parse','--path-format=absolute','--git-common-dir'],{encoding:'utf8'}).trim());
const out=path.join(root,'var/video/tomas');fs.mkdirSync(out,{recursive:true});
const evidence=JSON.parse(fs.readFileSync(path.join(root,'var/video/evidence.json')));
function chromePath(){if(process.env.CHROME_PATH)return process.env.CHROME_PATH;const base=path.join(os.homedir(),'Library/Caches/ms-playwright');if(fs.existsSync(base)){for(const p of fs.readdirSync(base).filter(p=>p.startsWith('chromium_headless_shell-')).reverse()){const f=path.join(base,p,'chrome-headless-shell-mac-arm64/chrome-headless-shell');if(fs.existsSync(f))return f;}}return undefined;}
const browser=await chromium.launch({headless:true,executablePath:chromePath()});const report=[];
async function shot(name,url,prepare){
 const context=await browser.newContext({viewport:{width:1440,height:810},recordVideo:{dir:out,size:{width:1920,height:1080}},reducedMotion:'reduce'});
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(url,{waitUntil:'domcontentloaded'});await page.waitForTimeout(2500);if(prepare)await prepare(page);
 await page.waitForTimeout(1200);await page.screenshot({path:path.join(out,name+'.png')});
 if(name==='approval') { const box=await page.locator('table').boundingBox(); await page.screenshot({path:path.join(out,'approval-detail.png'),clip:{x:box.x,y:Math.max(0,box.y-115),width:box.width,height:Math.min(350,810-Math.max(0,box.y-115))}}); }
 const start=Date.now();await page.mouse.move(1380,770);await page.waitForTimeout(7500);
 const vid=page.video();await context.close();await vid.saveAs(path.join(out,name+'.webm'));
 report.push({name,url,errors,hold_seconds:(Date.now()-start)/1000});console.log('Grabada',name);
}
try {
await shot('landing','http://localhost:5173');
await shot('patch','http://localhost:5173/app/parches',async p=>{
 await p.locator('#f-gen').fill('1');await p.locator('#f-variante').selectOption('rsi');await p.locator('#f-veredicto').selectOption('aceptado');await p.waitForTimeout(800);
 const button=p.getByRole('button',{name:'demo-seed42-'+evidence.patch.patch_id,exact:true});await button.click();await button.scrollIntoViewIfNeeded();
});
await shot('approval','http://localhost:5173/app/parches',async p=>{
 await p.locator('#f-corrida').selectOption('');await p.locator('#f-veredicto').selectOption('pendiente');await p.waitForTimeout(700);
 await p.getByRole('button',{name:/Aprobar parche video-revision/}).waitFor();
 // Show actual button without executing a decision on the production champion.
});
await shot('dashboard','http://localhost:8501',async p=>{await p.getByText('El RSI reduce el regret').first().waitFor();});
await shot('meta','http://localhost:8501',async p=>{
 await p.getByRole('tab',{name:'Aprende a mejorar'}).click();await p.getByRole('tab',{name:'Aprende a mejorar'}).scrollIntoViewIfNeeded();
});
await shot('lineage','http://localhost:8501',async p=>{
 await p.getByRole('tab',{name:'Versiones y garantías'}).click();await p.getByRole('tab',{name:'Versiones y garantías'}).scrollIntoViewIfNeeded();
});
}finally{await browser.close();fs.writeFileSync(path.join(out,'capture-report.json'),JSON.stringify(report,null,2));}
