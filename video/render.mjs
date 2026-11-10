import {fileURLToPath} from 'node:url';
import {browserPath} from './browser.mjs';
import {bundle} from '@remotion/bundler';
import {renderMedia,renderStill,selectComposition} from '@remotion/renderer';
import fs from 'node:fs';import path from 'node:path';import os from 'node:os';import {execFileSync} from 'node:child_process';
const dir=path.dirname(fileURLToPath(import.meta.url));
const root=path.dirname(execFileSync('git',['rev-parse','--path-format=absolute','--git-common-dir'],{encoding:'utf8'}).trim());const out=path.join(root,'var/video');
const pub=path.join(dir,'public');fs.mkdirSync(pub,{recursive:true});
for(const name of ['evidence.json','narration.json','audio','tomas'])fs.cpSync(path.join(out,name),path.join(pub,name),{recursive:true});

// Browser recordings are kept untouched; this separate excerpt omits page loading.
for(const name of ['dashboard']){
 const input=path.join(out,'tomas',name+'.webm');const probe=JSON.parse(execFileSync('ffprobe',['-v','error','-show_format','-of','json',input]));const duration=Number(probe.format.duration);const start=Math.max(0,duration-7);
 execFileSync('ffmpeg',['-v','error','-y','-ss',String(start),'-i',input,'-t','6.5','-vf','crop=1440:810:0:0,scale=1920:1080','-an','-c:v','libx264','-preset','fast','-crf','19',path.join(pub,'tomas',name+'.mp4')]);
}
const browserExecutable=browserPath();const serveUrl=await bundle({entryPoint:path.join(dir,'Root.jsx'),publicDir:pub});
const selected=process.env.VIDEO_ONLY?[process.env.VIDEO_ONLY]:['Demo','Fondo'];
for(const id of selected){
 const composition=await selectComposition({serveUrl,id,browserExecutable});
 if(process.argv.includes('--stills')){
  fs.mkdirSync(path.join(out,'qa'),{recursive:true});
  const times=id==='Demo'?[5,25,45,57,70,80,89,99,111,124,140,158,172]:[0,50,90,130,170,179.967];
  for(const t of times){await renderStill({serveUrl,composition,output:path.join(out,'qa',`${id}-${Math.round(t)}.png`),frame:Math.round(t*30),browserExecutable});console.log('Still',id,t);}continue;
 }
 let last=-1;
 await renderMedia({serveUrl,composition,browserExecutable,codec:'h264',outputLocation:path.join(out,id==='Demo'?'demo_3min.mp4':'fondo_pitch.mp4'),pixelFormat:'yuv420p',crf:19,x264Preset:'fast',concurrency:4,audioCodec:'aac',muted:id==='Fondo',onProgress:({progress})=>{const pct=Math.floor(progress*10)*10;if(pct!==last){last=pct;console.log(`${id}: ${pct}%`);}}});
 console.log('Rendered',id);
}
