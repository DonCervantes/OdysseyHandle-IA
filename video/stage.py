"""Stage an explicit pending replay for filming the real human-review button.

Uses only demo.db. Original decided patch and run artifacts are preserved.
"""
import json,os,subprocess,sys
from pathlib import Path
ROOT=Path(subprocess.check_output(['git','rev-parse','--path-format=absolute','--git-common-dir'],text=True).strip()).parent
os.environ['AUTOGUARD_NO_DOTENV']='1';os.environ['LLM_PROVIDER']='mock'
os.environ['DATABASE_URL']='sqlite:///'+str(ROOT/'var/demo.db')
sys.path.insert(0,str(ROOT))
from autoguard.contracts import Patch
from autoguard.db.session import session_scope
from autoguard.db.repo import save_patch
x=json.loads((ROOT/'var/video/evidence.json').read_text())['patch']
x.update(patch_id='video-revision-humana-rsi-'+x['patch_id'].removeprefix('rsi-'),veredicto=None,razon="Ensayo: decisión humana pendiente",
         hipotesis='ENSAYO DE REVISIÓN HUMANA: copia de una lección real, sin aplicar. '+x['hipotesis'])
with session_scope() as s:save_patch(s,Patch.model_validate(x))
print('Propuesta de ensayo guardada; no se aprobó ni alteró la tarifa.')
