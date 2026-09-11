#!/usr/bin/env python3
"""Aggregate v3.25 history diagnostics over 20 fresh fixed-depth searches."""
from __future__ import annotations
import argparse,json,re,sys
from dataclasses import dataclass,asdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from helpers.uci_engine import UCIEngine  # noqa: E402

BASELINE=Path('engine/c/zchezz_v325/zchezz_baseline.exe')
DIAGNOSTIC=Path('engine/c/zchezz_v325/zchezz_history_diag.exe')
SOURCE=Path('engine/c/zchezz_v325/main.c')
DEPTH=12; HASH_MB=64; OUTPUT=Path('artifacts/history-distribution')

@dataclass
class R: engine:str; position:int; nodes:int; bestmove:str; score:str|None

def load_fens(p):
 s=p.read_text(encoding='utf-8');m=re.search(r'BENCH_FENS\s*\[\s*\]\s*=\s*\{(.*?)\};',s,re.S);x=re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"',m.group(1)) if m else []
 if len(x)!=20:raise RuntimeError(f'expected20 FENs got {len(x)}')
 return x

def config(u):
 lines=u.handshake(timeout=20);names=set()
 for line in lines:
  m=re.match(r'option name (.+?)(?: type |$)',line)
  if m:names.add(m.group(1))
 for n,v in [('Threads',1),('Hash',HASH_MB),('MultiPV',1),('Ponder',False),('OwnBook',False)]:
  if n in names:u.setoption(n,v)
 u.send('isready');u.read_until(r'^readyok$',timeout=20)

def run(exe,name,fen,pos):
 u=UCIEngine(exe.resolve(),cwd=exe.resolve().parent)
 with u:
  config(u); lines=u.search(f'position fen {fen}',f'go depth {DEPTH}',timeout=120)
 if any('weights not loaded' in x.lower() for x in u.stderr):raise RuntimeError(f'{name}: NNUE load failure')
 info=next((x for x in reversed(lines) if x.startswith('info ') and ' nodes ' in x),'');nm=re.search(r'\bnodes\s+(\d+)',info);sm=re.search(r'\bscore\s+(cp|mate)\s+(-?\d+)',info);bm=next((x for x in reversed(lines) if x.startswith('bestmove ')),'').split()
 if not nm or len(bm)<2:raise RuntimeError(f'bad result {name} p{pos}')
 rec=R(name,pos,int(nm.group(1)),bm[1],f'{sm.group(1)} {sm.group(2)}' if sm else None)
 return rec,list(u.stderr)

def pct(a,b):return 100*a/b if b else 0

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--baseline',type=Path,default=BASELINE);ap.add_argument('--diagnostic',type=Path,default=DIAGNOSTIC);ap.add_argument('--source',type=Path,default=SOURCE);ap.add_argument('--output',type=Path,default=OUTPUT);a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 depths={d:{'samples':0,'neg':0,'le16':0,'le64':0,'le256':0,'le1024':0,'le4096':0,'current':0,'sum':0,'min':None,'max':None} for d in range(1,5)}; lmr={'samples':0,'lt_m4000':0,'lt_m8000':0,'gt_4000':0};records=[]
 for i,fen in enumerate(load_fens(a.source),1):
  b,_=run(a.baseline,'baseline',fen,i);d,err=run(a.diagnostic,'diagnostic',fen,i);records += [b,d]
  if (b.nodes,b.bestmove,b.score)!=(d.nodes,d.bestmove,d.score):raise RuntimeError(f'parity mismatch p{i}: {b} {d}')
  for line in err:
   if line.startswith('[HISTORY_DIAG]'):
    kv={k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',line)};z=depths[kv['depth']]
    for k in ['samples','neg','le16','le64','le256','le1024','le4096','current','sum']:z[k]+=kv[k]
    z['min']=kv['min'] if z['min'] is None else min(z['min'],kv['min']);z['max']=kv['max'] if z['max'] is None else max(z['max'],kv['max'])
   elif line.startswith('[HISTORY_LMR]'):
    kv={k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',line)}
    for k in lmr:lmr[k]+=kv[k]
 lines=['# v3.26 history-score distribution','',f'Exact baseline/diagnostic parity at depth **{DEPTH}** across 20 BENCH_FENS.','', '| Depth | samples | negative | <=-16 | <=-64 | <=-256 | <=-1024 | <=-4096 | current threshold hits | min | max | mean |','|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
 for dep,z in depths.items():
  mean=z['sum']/z['samples'] if z['samples'] else 0; lines.append(f"| {dep} | {z['samples']:,} | {z['neg']:,} ({pct(z['neg'],z['samples']):.1f}%) | {z['le16']:,} | {z['le64']:,} | {z['le256']:,} | {z['le1024']:,} | {z['le4096']:,} | {z['current']:,} | {z['min']} | {z['max']} | {mean:.1f} |")
 lines += ['', '## Current LMR history-adjustment thresholds','', f"- samples: **{lmr['samples']:,}**", f"- `ch < -4000`: **{lmr['lt_m4000']:,}** ({pct(lmr['lt_m4000'],lmr['samples']):.3f}%)", f"- `ch < -8000`: **{lmr['lt_m8000']:,}** ({pct(lmr['lt_m8000'],lmr['samples']):.3f}%)", f"- `ch > 4000`: **{lmr['gt_4000']:,}** ({pct(lmr['gt_4000'],lmr['samples']):.3f}%)",'']
 report='\n'.join(lines);print(report);(a.output/'summary.md').write_text(report,encoding='utf-8');(a.output/'metrics.json').write_text(json.dumps({'depths':depths,'lmr':lmr,'records':[asdict(r) for r in records]},indent=2)+'\n',encoding='utf-8');return 0
if __name__=='__main__':raise SystemExit(main())
