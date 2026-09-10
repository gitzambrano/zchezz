#!/usr/bin/env python3
"""Architecture-neutral Stockfish teacher. Bare run labels data/teacher_input.epd."""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import chess, chess.engine
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'utils'))
from engine_profiles import stockfish_executable
INPUT=ROOT/'data/teacher_input.epd'; OUTPUT=ROOT/'data/teacher_stockfish.epd'; DEPTH=12
def _fen(line:str)->str:
    fields=line.split()
    if len(fields)<4: raise ValueError('EPD line has fewer than four FEN fields')
    return ' '.join(fields[:4])+' 0 1'
def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--input',type=Path,default=INPUT); ap.add_argument('--output',type=Path,default=OUTPUT); ap.add_argument('--depth',type=int,default=DEPTH); ap.add_argument('--show-config',action='store_true'); a=ap.parse_args(); sf=stockfish_executable()
    if a.show_config: print(f'input={a.input}\noutput={a.output}\ndepth={a.depth}\nstockfish={sf or "not found"}'); return 0
    if sf is None: print('Stockfish not found. Set ZCHEZZ_STOCKFISH, install under engine/stockfish/, or put stockfish on PATH.'); return 2
    if not a.input.is_file(): print(f'Input EPD not found: {a.input}'); return 2
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with chess.engine.SimpleEngine.popen_uci(str(sf)) as eng, a.input.open(encoding='utf-8') as src, a.output.open('w',encoding='utf-8') as dst:
        for raw in src:
            s=raw.strip()
            if not s or s.startswith('#'): continue
            board=chess.Board(_fen(s)); info=eng.analyse(board,chess.engine.Limit(depth=a.depth)); score=info['score'].pov(chess.WHITE).score(mate_score=100000)
            if score is None: score=0
            dst.write(f'{" ".join(s.split()[:4])} c1 "{int(score)}"; c2 "Stockfish";\n')
    return 0
if __name__=='__main__': raise SystemExit(main())
