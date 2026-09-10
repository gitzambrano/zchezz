#!/usr/bin/env python3
"""Export a v500 HalfKP-4-Bucket checkpoint to NNU4."""
from __future__ import annotations
import argparse, struct
from pathlib import Path
import numpy as np, torch
ROOT=Path(__file__).resolve().parents[1]; L1_IN=2560; L1_OUT=48; L2_IN=96; L2_OUT=20; L3_IN=20
QA=255.0; QB=64.0; SHIFT=8.0; QA_EFF=254.0; OUT_SCALE=320.0/(QB*QB); EXPECTED_SIZE=248_020
DEFAULT_CKPT=ROOT/'checkpoints/v500/latest.pt'; DEFAULT_DST=ROOT/'artifacts/nnu4/nnue_weights.bin'
def _q(a,scale,limit,dtype,name):
    q=np.rint(a*scale); n=int((np.abs(q)>limit).sum())
    if n: print(f'WARNING: clipping {n} {name} values')
    return np.clip(q,-limit,limit).astype(dtype)
def convert(ckpt_path:Path,dst:Path):
    ckpt=torch.load(ckpt_path,map_location='cpu',weights_only=False)
    arch=ckpt.get('arch',{}); expected={'input':L1_IN,'h1':L1_OUT,'concat':L2_IN,'h2':L2_OUT,'encoding':'halfkp_4bucket'}
    for k,v in expected.items():
        if arch.get(k)!=v: raise ValueError(f'incompatible checkpoint {k}={arch.get(k)!r}, expected {v!r}')
    w=ckpt.get('weights',ckpt); arr=lambda k:w[k].detach().cpu().numpy().astype(np.float32)
    l1w,l1b,l2w,l2b,l3w,l3b=arr('l1.weight'),arr('l1_bias'),arr('l2.weight'),arr('l2.bias'),arr('l3.weight'),arr('l3.bias')
    if l1w.shape!=(L1_IN,L1_OUT) or l1b.shape!=(L1_OUT,) or l2w.shape!=(L2_OUT,L2_IN) or l2b.shape!=(L2_OUT,) or l3w.reshape(-1).shape!=(L3_IN,): raise ValueError('checkpoint tensor shape mismatch')
    dst.parent.mkdir(parents=True,exist_ok=True)
    with dst.open('wb') as f:
        f.write(b'NNU4'); f.write(struct.pack('<I',int(ckpt.get('epoch',0)))); f.write(struct.pack('<5I',L1_IN,L1_OUT,L2_IN,L2_OUT,L3_IN)); f.write(struct.pack('<4f',QA,QB,SHIFT,OUT_SCALE)); f.write(np.ascontiguousarray(_q(l1w,QA,32767,'<i2','L1W')).tobytes()); f.write(np.rint(l1b*QA).astype('<i4').tobytes()); f.write(np.ascontiguousarray(_q(l2w,QB,127,'i1','L2W')).tobytes()); f.write(np.rint(l2b*QA_EFF*QB).astype('<i4').tobytes()); f.write(_q(l3w.reshape(-1),QB,127,'i1','L3W').tobytes()); f.write(struct.pack('<f',float(l3b.reshape(-1)[0])))
    if dst.stat().st_size!=EXPECTED_SIZE: dst.unlink(missing_ok=True); raise ValueError('NNU4 size mismatch')
    print(f'NNU4 export: {ckpt_path} -> {dst} ({EXPECTED_SIZE} bytes)')
def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--checkpoint',type=Path,default=DEFAULT_CKPT); p.add_argument('--output',type=Path,default=DEFAULT_DST); a=p.parse_args(); convert(a.checkpoint,a.output); return 0
if __name__=='__main__': raise SystemExit(main())
