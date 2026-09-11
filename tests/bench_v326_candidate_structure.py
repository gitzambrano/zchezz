#!/usr/bin/env python3
"""Fresh-process fixed-depth structural comparison for one v3.26 candidate."""
from __future__ import annotations
import argparse, json, re, statistics, sys, time
from dataclasses import asdict, dataclass
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers.uci_engine import UCIEngine  # noqa: E402

BASELINE=Path("engine/c/zchezz_v325/zchezz_baseline.exe")
CANDIDATE=Path("engine/c/zchezz_v325/zchezz_candidate.exe")
SOURCE=Path("engine/c/zchezz_v325/main.c")
DEPTHS=(8,10,12)
HASH_MB=64
OUTPUT=Path("artifacts/v326-candidate-structure")

@dataclass
class R:
    engine:str; depth:int; position:int; nodes:int; bestmove:str; score:str|None; elapsed_ms:float

def fens(path:Path)->list[str]:
    s=path.read_text(encoding="utf-8"); m=re.search(r"BENCH_FENS\s*\[\s*\]\s*=\s*\{(.*?)\};",s,re.S)
    if not m: raise RuntimeError("BENCH_FENS not found")
    x=re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"',m.group(1))
    if len(x)!=20: raise RuntimeError(f"expected 20 FENs, got {len(x)}")
    return x

def config(u:UCIEngine):
    lines=u.handshake(timeout=20); names=set()
    for line in lines:
        m=re.match(r"option name (.+?)(?: type |$)",line)
        if m:names.add(m.group(1))
    for n,v in (("Threads",1),("Hash",HASH_MB),("MultiPV",1),("Ponder",False),("OwnBook",False)):
        if n in names:u.setoption(n,v)
    u.send("isready");u.read_until(r"^readyok$",timeout=20)

def run(exe:Path,name:str,fen:str,depth:int,pos:int)->R:
    u=UCIEngine(exe.resolve(),cwd=exe.resolve().parent)
    with u:
        config(u); t=time.monotonic(); lines=u.search(f"position fen {fen}",f"go depth {depth}",timeout=120); elapsed=(time.monotonic()-t)*1000
    if any("weights not loaded" in x.lower() for x in u.stderr): raise RuntimeError(f"{name}: NNUE load failure")
    info=next((x for x in reversed(lines) if x.startswith("info ") and " nodes " in x),"")
    nm=re.search(r"\bnodes\s+(\d+)",info); sm=re.search(r"\bscore\s+(cp|mate)\s+(-?\d+)",info)
    bm=next((x for x in reversed(lines) if x.startswith("bestmove ")),"").split()
    if not nm or len(bm)<2: raise RuntimeError(f"bad result {name} d{depth} p{pos}")
    return R(name,depth,pos,int(nm.group(1)),bm[1],f"{sm.group(1)} {sm.group(2)}" if sm else None,elapsed)

def main()->int:
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--baseline",type=Path,default=BASELINE);ap.add_argument("--candidate",type=Path,default=CANDIDATE);ap.add_argument("--source",type=Path,default=SOURCE);ap.add_argument("--output",type=Path,default=OUTPUT);a=ap.parse_args()
    fs=fens(a.source);a.output.mkdir(parents=True,exist_ok=True);records=[];summary={}
    for d in DEPTHS:
        b=[];c=[]
        for i,fen in enumerate(fs,1):
            rb=run(a.baseline,"baseline",fen,d,i);rc=run(a.candidate,"candidate",fen,d,i);b.append(rb);c.append(rc);records += [rb,rc]
        bn=sum(x.nodes for x in b);cn=sum(x.nodes for x in c);bt=sum(x.elapsed_ms for x in b);ct=sum(x.elapsed_ms for x in c)
        diffs=sum((x.bestmove,x.score)!=(y.bestmove,y.score) for x,y in zip(b,c))
        summary[str(d)]={"baseline_nodes":bn,"candidate_nodes":cn,"node_delta_pct":(cn/bn-1)*100,"baseline_elapsed_ms":bt,"candidate_elapsed_ms":ct,"elapsed_delta_pct":(ct/bt-1)*100,"result_diffs":diffs,"median_baseline_nodes":statistics.median(x.nodes for x in b),"median_candidate_nodes":statistics.median(x.nodes for x in c)}
    lines=["# v3.26 isolated candidate structural screen","","Fresh process per FEN; Threads 1; Hash 64 MB; 20 BENCH_FENS.","","| Depth | Baseline nodes | Candidate nodes | Node delta | Wall-time delta | bestmove/score diffs |","|---:|---:|---:|---:|---:|---:|"]
    for d in DEPTHS:
        s=summary[str(d)];lines.append(f"| {d} | {s['baseline_nodes']:,} | {s['candidate_nodes']:,} | {s['node_delta_pct']:+.2f}% | {s['elapsed_delta_pct']:+.2f}% | {s['result_diffs']}/20 |")
    lines += ["","Fixed-depth node reduction is only a structural screen; strength requires 200 ms H2H.",""]
    report="\n".join(lines);print(report)
    (a.output/"summary.md").write_text(report,encoding="utf-8");(a.output/"metrics.json").write_text(json.dumps({"summary":summary,"records":[asdict(x) for x in records]},indent=2)+"\n",encoding="utf-8");return 0
if __name__=="__main__":raise SystemExit(main())
