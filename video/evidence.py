"""Build auditable video inputs from artifacts; never reads credentials or edits the run."""
from __future__ import annotations
import hashlib,json,os,re,subprocess,sys
from pathlib import Path
os.environ['AUTOGUARD_NO_DOTENV']='1'
os.environ['LLM_PROVIDER']='mock'
ROOT=Path(subprocess.check_output(['git','rev-parse','--path-format=absolute','--git-common-dir'],text=True).strip()).parent
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
import yaml
from git import Repo
from autoguard.config_schema import CotizadorConfig
from autoguard.agents.cotizador import quote_df
from autoguard.contracts import Patch
from autoguard.evaluator.evaluator import split_holdout,evaluate
from autoguard.evaluator import objective
from autoguard.rsi.analista import analyze
from autoguard.rsi.recolector import collect
from autoguard.sim.market import MarketSimulator

OUT=ROOT/'var/video'
RUN=ROOT/'var/runs/demo-seed42'
def lines(name): return [json.loads(x) for x in (RUN/name).read_text().splitlines() if x.strip()]
def cmd(*args): return subprocess.check_output(args,cwd=ROOT,text=True).strip()
def cfg(commit): return CotizadorConfig.model_validate(yaml.safe_load((commit.tree/'config.yaml').data_stream.read()))
def build():
    OUT.mkdir(parents=True,exist_ok=True)
    summary=json.loads((RUN/'summary.json').read_text())
    assert summary['simulados'] is True
    patches=lines('patches.jsonl'); versions=lines('versions.jsonl');meta=lines('meta.jsonl')
    repo=Repo(RUN/'configs/rsi');commits=list(reversed(list(repo.iter_commits())))
    initial=cfg(commits[0]); successor=cfg(commits[1]); payload=json.loads(commits[1].message)
    patch=next(p for p in patches if p['variant']=='rsi' and p['patch_id'].removeprefix('rsi-')==payload['patch_id'])
    assert patch['generation']==1 and patch['veredicto']=='aceptado'
    sim=MarketSimulator(summary['seed']); closed=[]
    for _ in range(summary['k']):
        b=sim.sample_batch(summary['batch_size']);prices=quote_df(b,initial)
        pred=b.assign(prima=prices,prediction_id=b.vehicle_id,agent_version='cotizador@'+commits[0].hexsha[:7])
        outcomes=sim.resolve(b,prices);outcomes['prediction_id']=b.vehicle_id.to_numpy()
        closed.append(collect(pred,outcomes))
    train,holdout=split_holdout(pd.concat(closed,ignore_index=True))
    hypothesis=next(h for h in analyze(train,top_k=12) if h.segmento==patch['segmento'])
    verdict,_=evaluate(initial,Patch.model_validate(payload).model_copy(update={'veredicto':None}),holdout)
    assert verdict.aceptado
    before=quote_df(holdout,initial); after=quote_df(holdout,successor)
    assert np.isclose(objective.loss(before,holdout.costo_real).mean(),patch['metrics_before']['loss'])
    assert np.isclose(objective.loss(after,holdout.costo_real).mean(),patch['metrics_after']['loss'])
    from autoguard.segments import segment_mask
    candidates=holdout.loc[segment_mask(holdout,patch['segmento'])].copy()
    # Select nearest to median cost/price in the diagnosed segment, never maximum gain.
    ratios=candidates.costo_real/candidates.prima
    row=candidates.loc[(ratios-ratios.median()).abs().idxmin()]
    one=pd.DataFrame([row]);cost=float(row.costo_real)
    # Revert the lesson in an isolated Git clone; original lineage remains immutable.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        clone=Repo.clone_from(str(repo.working_tree_dir),tmp)
        clone.git.checkout('--detach',commits[1].hexsha)
        from autoguard.rsi.lineage import ConfigRepo
        local=ConfigRepo(tmp);revert_sha=local.revert_to(commits[0].hexsha,'Ablación de la primera lección; copia aislada para video')
        reverted,_=local.current()
        assert reverted==initial
        quotes={'v0':float(quote_df(one,initial)[0]),'sucesor':float(quote_df(one,successor)[0]),'reversion':float(quote_df(one,reverted)[0]),'final':float(quote_df(one,cfg(commits[-1]))[0])}
    assert quotes['v0']==quotes['reversion']
    control=Repo(RUN/'configs/parametros')
    quotes['parametros_final']=float(quote_df(one,cfg(control.head.commit))[0])
    case={k:(v.item() if isinstance(v,np.generic) else v) for k,v in row.to_dict().items()}
    case.update(quotes=quotes,losses={k:float(objective.loss(v,cost)) for k,v in quotes.items()})
    # Three held-out observations, chosen by stable ID, with actual prices under both configs.
    examples=[]
    for _,r in candidates.sort_values('vehicle_id').head(3).iterrows():
        frame=pd.DataFrame([r]);examples.append({'vehicle_id':r.vehicle_id,'costo_real':r.costo_real,'v0':float(quote_df(frame,initial)[0]),'sucesor':float(quote_df(frame,successor)[0])})
    text=(ROOT/'RELEVO.md').read_text();seeds=[]
    for m in re.finditer(r'\| (42|1|7|123) \| ([\d.]+)M \| ([\d.]+)M \(−([\d.]+)%\) \| \*\*([\d.]+)M \(−([\d.]+)%\)\*\*',text):
        seed,est,par,par_pct,rsi,pct=m.groups();seeds.append(dict(seed=int(seed),estatico=float(est)*1e6,parametros=float(par)*1e6,rsi=float(rsi)*1e6,mejora=float(pct)))
    assert len(seeds)==4
    inventory={'owned':[],'reviewed':[]}
    for name in cmd('git','ls-tree','--name-only','origin/tasks-state').splitlines():
        if not re.fullmatch(r'T-\d+',name):continue
        for field,target in [('owner','owned'),('reviewer','reviewed')]:
            proc=subprocess.run(['git','show',f'origin/tasks-state:{name}/{field}'],cwd=ROOT,capture_output=True,text=True)
            if proc.returncode==0 and proc.stdout.startswith('gpt-dylan:'):inventory[target].append(name)
    inventory['first_commit']=cmd('git','log','--reverse','--format=%h|%aI|%s').splitlines()[0]
    inventory['git_log']=cmd('git','log','--all','--format=%h %s','--grep=gpt-dylan')
    sources={name:hashlib.sha256((RUN/name).read_bytes()).hexdigest() for name in ['summary.json','curve.csv','patches.jsonl','versions.jsonl','meta.jsonl']}
    evidence=dict(summary=summary,patch=patch,hypothesis=hypothesis.model_dump(),case=case,holdout_examples=examples,
        holdout_n=len(holdout),train_n=len(train),lineage=[{'sha':c.hexsha,'message':c.message} for c in commits],
        parent_sha=commits[0].hexsha,successor_sha=commits[1].hexsha,revert_sha=revert_sha,
        yaml_diff=repo.git.diff(commits[0].hexsha,commits[1].hexsha,'--','config.yaml'),meta=meta,versions=versions,
        curves=pd.read_csv(RUN/'curve.csv').to_dict('records'),seeds=seeds,inventory=inventory,sha256=sources,
        accepted_count=sum(p['variant']=='rsi' and p['veredicto']=='aceptado' for p in patches),
        constants={k:getattr(objective,k) for k in ['ALPHA','BETA','DELTA','EPSILON','HOLDOUT_FRACTION']},
        external_context={'label':'7 de cada 10 vehículos sin seguro','source':'AMIS citada por Animal Político, 27 julio 2026','url':'https://grupoanimal.mx/hablemos-de/mexico-mas-vehiculos-pocos-seguros-qualitas-record'},
        selection='Mediana de costo/prima en el segmento diagnosticado del holdout de generación 1. No se eligió por máxima mejora.',
        caveat='El mejorador no ve filas de holdout. El evaluador reutiliza el holdout y devuelve métricas; no es un test externo nunca consultado.')
    (OUT/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    print(json.dumps({'case':case,'hypothesis':evidence['hypothesis'],'owned':inventory['owned'],'reviewed':inventory['reviewed']},ensure_ascii=False,indent=2))
if __name__=='__main__':build()
