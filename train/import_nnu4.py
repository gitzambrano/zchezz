#!/usr/bin/env python3
"""Convert installed/explicit NNU4 weights to a resumable PyTorch checkpoint."""
from __future__ import annotations
import argparse, math, struct
from pathlib import Path
import numpy as np, torch
ROOT=Path(__file__).resolve().parents[1]; DEFAULT_SRC=ROOT/'engine/c/zchezz_v500/nnue_weights.bin'; DEFAULT_DST=ROOT/'checkpoints/v500/latest.pt'
QA=255.0; QB=64.0; SHIFT=8.0; OUT_SCALE=320.0/(QB*QB)

def read_nnu4(path: Path):
    data=path.read_bytes(); off=0
    if data[:4]!=b'NNU4': raise ValueError(f'{path}: expected NNU4')
    off=4; epoch=struct.unpack_from('<I',data,off)[0]; off+=4; l1_in,l1_out,l2_in,l2_out,l3_in=struct.unpack_from('<5I',data,off); off+=20
    if l1_in!=2560 or l2_in!=2*l1_out or l3_in!=l2_out: raise ValueError('invalid NNU4 architecture')
    qa,qb,shift,out=struct.unpack_from('<4f',data,off); off+=16
    for got,exp,name in ((qa,QA,'QA'),(qb,QB,'QB'),(shift,SHIFT,'SHIFT'),(out,OUT_SCALE,'OUT_SCALE')):
        if not math.isclose(got,exp,rel_tol=0,abs_tol=1e-7): raise ValueError(f'{name} mismatch')
    qa_eff=int((qa*qa)//(1<<int(shift)))
    def take(dtype,count):
        nonlocal off
        dt=np.dtype(dtype).newbyteorder('<'); n=dt.itemsize*count
        if off+n>len(data): raise ValueError('truncated NNU4')
        a=np.frombuffer(data,dtype=dt,count=count,offset=off).copy(); off+=n; return a
    w={'l1.weight':torch.from_numpy(take('i2',l1_in*l1_out).reshape(l1_in,l1_out).astype(np.float32)/qa),'l1_bias':torch.from_numpy(take('i4',l1_out).astype(np.float32)/qa),'l2.weight':torch.from_numpy(take('i1',l2_out*l2_in).reshape(l2_out,l2_in).astype(np.float32)/qb),'l2.bias':torch.from_numpy(take('i4',l2_out).astype(np.float32)/(qa_eff*qb)),'l3.weight':torch.from_numpy(take('i1',l3_in).reshape(1,l3_in).astype(np.float32)/qb)}
    w['l3.bias']=torch.tensor([struct.unpack_from('<f',data,off)[0]],dtype=torch.float32); off+=4
    if off!=len(data): raise ValueError('trailing NNU4 bytes')
    return w,{'input':l1_in,'h1':l1_out,'concat':l2_in,'h2':l2_out,'encoding':'halfkp_4bucket'},int(epoch)

def convert(src:Path,dst:Path):
    weights,arch,epoch=read_nnu4(src); dst.parent.mkdir(parents=True,exist_ok=True); tmp=dst.with_suffix(dst.suffix+'.tmp')
    torch.save({'epoch':epoch,'dataset':'bootstrap_v500','arch':arch,'qat':True,'qa':QA,'qb':QB,'weights':weights,'bootstrap':{'source':str(src)}},tmp); tmp.replace(dst); print(f'NNU4 checkpoint: {src} -> {dst}')

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--src',type=Path,default=DEFAULT_SRC); p.add_argument('--dst',type=Path,default=DEFAULT_DST); a=p.parse_args(); convert(a.src,a.dst); return 0
if __name__=='__main__': raise SystemExit(main())
