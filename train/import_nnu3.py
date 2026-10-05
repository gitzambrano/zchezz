#!/usr/bin/env python3
"""Convert installed/explicit NNU3 weights to a resumable PyTorch checkpoint."""
from __future__ import annotations
import argparse, struct
from pathlib import Path
import numpy as np, torch
ROOT=Path(__file__).resolve().parents[1]
DEFAULT_SRC=ROOT/'engine/c/zchezz_v325/nnue_weights.bin'
DEFAULT_DST=ROOT/'checkpoints/v325/latest.pt'
QA=255.0; QB=64.0
EXPECTED_DIMS=(799,256,256,64,64); EXPECTED_SIZE=426_864

def read_nnu3(path:Path):
    data=path.read_bytes()
    if len(data)!=EXPECTED_SIZE or data[:4]!=b'NNU3': raise ValueError(f'{path}: invalid NNU3 artifact')
    epoch=struct.unpack_from('<I',data,4)[0]; dims=struct.unpack_from('<5I',data,8)
    if dims!=EXPECTED_DIMS: raise ValueError(f'{path}: NNU3 dims {dims} != {EXPECTED_DIMS}')
    off=44
    def take(dtype,count):
        nonlocal off
        dt=np.dtype(dtype).newbyteorder('<'); n=dt.itemsize*count; a=np.frombuffer(data,dtype=dt,count=count,offset=off).copy(); off+=n; return a
    l1w=(take('i2',799*256).reshape(799,256).astype(np.float32)/QA).T.copy(); l1b=take('i4',256).astype(np.float32)/QA
    l2w=(take('i1',256*64).reshape(256,64).astype(np.float32)/QB).T.copy(); l2b=take('i4',64).astype(np.float32)/(QA*QB)
    l3w=take('i1',64).astype(np.float32).reshape(1,64)/QB; l3b=np.frombuffer(data,dtype='<f4',count=1,offset=off).copy(); off+=4
    if off!=len(data): raise ValueError('NNU3 trailing bytes')
    state={k:torch.from_numpy(v) for k,v in {'l1.weight':l1w,'l1.bias':l1b,'l2.weight':l2w,'l2.bias':l2b,'l3.weight':l3w,'l3.bias':l3b}.items()}
    arch={'input':799,'h1':256,'h2':64,'encoding':'nnu3_hm_768_plus_31','format':'NNU3'}
    return state,arch,int(epoch)

def convert(src:Path,dst:Path):
    state,arch,epoch=read_nnu3(src); dst.parent.mkdir(parents=True,exist_ok=True); tmp=dst.with_suffix(dst.suffix+'.tmp')
    torch.save({'format':'zchezz_nnu3_checkpoint_v1','arch':arch,'dataset_name':'bootstrap_v325','epoch':epoch,'lr':1e-3,'model':state,'optimizer':None,'metrics':{},'bootstrap':{'source':str(src)}},tmp)
    tmp.replace(dst); print(f'NNU3 checkpoint: {src} -> {dst}')

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--src',type=Path,default=DEFAULT_SRC); p.add_argument('--dst',type=Path,default=DEFAULT_DST); a=p.parse_args(); convert(a.src,a.dst); return 0
if __name__=='__main__': raise SystemExit(main())
