#!/usr/bin/env python3
"""Aggregate v3.27 LMR-history diagnostics over 20 fresh depth-12 searches."""
from __future__ import annotations
import argparse,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from helpers.uci_engine import UCIEngine

BASE=Path('engine/c/zchezz_v326/zchezz_baseline.exe')
DIAG=Path('engine/c/zchezz_v326/zchezz_diag.exe')
SOURCE=Path('engine/c/zchezz_v326/main.c')
OUT=Path('artifacts/v327-lmr-history')
DEPTH=12


def fens(path:Path):
    s=path.read_text(encoding='utf-8');m=re.search(r'BENCH_FENS\s*\[\s*\]\s*=\s*\{(.*?)\};',s,re.S)
    xs=re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"',m.group(1)) if m else []
    if len(xs)!=20: raise RuntimeError(f'expected 20 FENs, got {len(xs)}')
    return xs


def config(u):
    lines=u.handshake(timeout=20);names=set()
    for line in lines:
        m=re.match(r'option name (.+?)(?: type |$)',line)
        if m:names.add(m.group(1))
    for n,v in [('Threads',1),('Hash',64),('MultiPV',1),('Ponder',False),('OwnBook',False)]:
        if n in names:u.setoption(n,v)
    u.send('isready');u.read_until(r'^readyok$',timeout=20)


def run(exe:Path,fen:str):
    u=UCIEngine(exe.resolve(),cwd=exe.resolve().parent)
    with u:
        config(u);lines=u.search(f'position fen {fen}',f'go depth {DEPTH}',timeout=120)
    info=next((x for x in reversed(lines) if x.startswith('info ') and ' nodes ' in x),'')
    nm=re.search(r'\bnodes\s+(\d+)',info);bm=next((x for x in reversed(lines) if x.startswith('bestmove ')),'').split()
    sm=re.search(r'\bscore\s+(cp|mate)\s+(-?\d+)',info)
    if not nm or len(bm)<2: raise RuntimeError('bad engine result')
    return (int(nm.group(1)),bm[1],f'{sm.group(1)} {sm.group(2)}' if sm else None),list(u.stderr)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--baseline',type=Path,default=BASE);ap.add_argument('--diagnostic',type=Path,default=DIAG);ap.add_argument('--source',type=Path,default=SOURCE);ap.add_argument('--output',type=Path,default=OUT);a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    keys=['samples','lt_m1024','lt_m768','lt_m640','lt_m512','lt_m384','gt_384','gt_512','gt_640','gt_768','gt_1024','gt_2048','sum']
    z={d:{k:0 for k in keys}|{'min':None,'max':None} for d in ['3','4','5','6+']}
    for i,fen in enumerate(fens(a.source),1):
        rb,_=run(a.baseline,fen);rd,err=run(a.diagnostic,fen)
        if rb!=rd: raise RuntimeError(f'parity mismatch p{i}: {rb} != {rd}')
        for line in err:
            if not line.startswith('[V327_LMR_HIST]'): continue
            dep=re.search(r'depth=(3|4|5|6\+)',line).group(1);vals={k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',line)};r=z[dep]
            for k in keys:r[k]+=vals[k]
            r['min']=vals['min'] if r['min'] is None else min(r['min'],vals['min']);r['max']=vals['max'] if r['max'] is None else max(r['max'],vals['max'])
    def pct(n,d): return 100*n/d if d else 0.0
    lines=['# v3.27 LMR history distribution','',f'Exact parity with v3.26 at depth {DEPTH} across 20 BENCH_FENS.','',
           '| Depth | Samples | <-1024 | <-768 | <-640 | <-512 | <-384 | >384 | >512 | >640 | >768 | >1024 | >2048 | Mean | Range |',
           '|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for dep in ['3','4','5','6+']:
        r=z[dep];n=r['samples'];mean=r['sum']/n if n else 0
        def cell(k):return f"{r[k]:,} ({pct(r[k],n):.1f}%)"
        lines.append(f"| {dep} | {n:,} | {cell('lt_m1024')} | {cell('lt_m768')} | {cell('lt_m640')} | {cell('lt_m512')} | {cell('lt_m384')} | {cell('gt_384')} | {cell('gt_512')} | {cell('gt_640')} | {cell('gt_768')} | {cell('gt_1024')} | {cell('gt_2048')} | {mean:.1f} | {r['min']}..{r['max']} |")
    report='\n'.join(lines)+'\n';print(report);(a.output/'summary.md').write_text(report,encoding='utf-8');(a.output/'metrics.json').write_text(json.dumps(z,indent=2)+'\n',encoding='utf-8');return 0

if __name__=='__main__':raise SystemExit(main())
