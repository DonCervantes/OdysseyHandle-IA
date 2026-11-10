"""Verify actual streams, timeline, evidence identity and loop seam; export an audit report."""
import json,hashlib,subprocess
from pathlib import Path
import numpy as np
ROOT=Path(subprocess.check_output(['git','rev-parse','--path-format=absolute','--git-common-dir'],text=True).strip()).parent
OUT=ROOT/'var/video'
e=json.loads((OUT/'evidence.json').read_text());n=json.loads((OUT/'narration.json').read_text())
report={'artifacts':{},'videos':{},'warnings':[]}
for name,expected in e['sha256'].items():
    actual=hashlib.sha256((ROOT/'var/runs/demo-seed42'/name).read_bytes()).hexdigest()
    assert actual==expected, f'Artifact changed after evidence generation: {name}'
    report['artifacts'][name]=actual
for name in ['demo_3min.mp4','fondo_pitch.mp4']:
    p=OUT/name
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)],text=True))
    video=next(s for s in probe['streams'] if s['codec_type']=='video')
    audio=[s for s in probe['streams'] if s['codec_type']=='audio']
    duration=float(probe['format']['duration'])
    assert video['width']==1920 and video['height']==1080
    assert duration<=180.001 and duration>=179.9
    assert video['codec_name']=='h264'
    assert bool(audio)==(name=='demo_3min.mp4')
    report['videos'][name]={'duration_seconds':duration,'width':video['width'],'height':video['height'],'audio_streams':len(audio),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
for segment in n:
    duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(OUT/segment['audio'])],text=True))
    assert duration<=segment['end']-segment['start']+0.02
    if segment['id']=='09':assert segment['start']+duration<=178.05

def frame(t):
    return np.frombuffer(subprocess.check_output(['ffmpeg','-v','error','-ss',str(t),'-i',str(OUT/'fondo_pitch.mp4'),'-frames:v','1','-vf','scale=480:270','-pix_fmt','rgb24','-f','rawvideo','-']),dtype=np.uint8).astype(float)
a,b=frame(0),frame(179.9667)
assert a.shape==b.shape and len(a)>0
seam=float(abs(a-b).mean());report['loop_seam_mean_absolute_rgb_difference']=seam
assert seam<2,'Loop seam is visible: first/last frames differ'
assert e['case']['quotes']['v0']==e['case']['quotes']['reversion']
assert e['case']['losses']['v0']==e['case']['losses']['reversion']
assert all(not s['errors'] for s in json.loads((OUT/'tomas/capture-report.json').read_text()))
(OUT/'verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report['videos'],indent=2));print('Loop seam MAE:',seam)
