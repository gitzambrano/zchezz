#!/usr/bin/env python3
from pathlib import Path

root=Path('engine/c/zchezz_v323')
main=root/'main.c'; s=main.read_text(encoding='utf-8')
old='#define ENGINE_VERSION "3.23"'
if s.count(old)!=1: raise SystemExit(f'version anchor count={s.count(old)}')
main.write_text(s.replace(old,'#define ENGINE_VERSION "3.30"',1),encoding='utf-8')

h=root/'search.h'; s=h.read_text(encoding='utf-8')
pairs=[
 ('extern uint64_t TT_H[TT_SIZE];','extern uint32_t TT_H[TT_SIZE];'),
 ('extern int32_t  TT_S[TT_SIZE];','extern int16_t  TT_S[TT_SIZE];'),
 ('extern int32_t  TT_D[TT_SIZE];','extern uint16_t TT_D[TT_SIZE];'),
 ('extern uint16_t TT_G[TT_SIZE];','extern uint8_t  TT_G[TT_SIZE];'),
 ('extern int32_t  TT_M[TT_SIZE];','extern uint32_t TT_M[TT_SIZE];'),
 ('extern int32_t  TT_E[TT_SIZE];','extern int16_t  TT_E[TT_SIZE];'),
 ('extern uint16_t TT_GEN;','extern uint8_t TT_GEN;'),
]
for a,b in pairs:
 if s.count(a)!=1: raise SystemExit(f'header anchor {a!r} count={s.count(a)}')
 s=s.replace(a,b,1)
h.write_text(s,encoding='utf-8')

p=root/'search.c'; s=p.read_text(encoding='utf-8')
defs=[
 ('uint64_t TT_H[TT_SIZE];','uint32_t TT_H[TT_SIZE];'),
 ('int32_t  TT_S[TT_SIZE];','int16_t  TT_S[TT_SIZE];'),
 ('int32_t  TT_D[TT_SIZE];','uint16_t TT_D[TT_SIZE];'),
 ('uint16_t TT_G[TT_SIZE];','uint8_t  TT_G[TT_SIZE];'),
 ('int32_t  TT_M[TT_SIZE];','uint32_t TT_M[TT_SIZE];'),
 ('int32_t  TT_E[TT_SIZE];','int16_t  TT_E[TT_SIZE];'),
 ('uint16_t TT_GEN = 0;','uint8_t TT_GEN = 0;'),
]
for a,b in defs:
 if s.count(a)!=1: raise SystemExit(f'def anchor {a!r} count={s.count(a)}')
 s=s.replace(a,b,1)

a='''    int slot = (int)(hash & TT_MASK);
    int base = slot * TT_BUCKETS;
    int stored_score = tt_score_store(score, ply);'''
b='''    int slot = (int)(hash & TT_MASK);
    int base = slot * TT_BUCKETS;
    /* Lower hash bits choose the slot, upper 32 bits are the signature. */
    uint32_t key32 = (uint32_t)(hash >> 32);
    int stored_score = tt_score_store(score, ply);'''
if s.count(a)!=1: raise SystemExit(f'store anchor count={s.count(a)}')
s=s.replace(a,b,1)
for a,b in [
 ('TT_H[base] = hash; TT_S[base] = stored_score;', 'TT_H[base] = key32; TT_S[base] = (int16_t)stored_score;'),
 ('TT_H[base+1] = hash; TT_S[base+1] = stored_score;', 'TT_H[base+1] = key32; TT_S[base+1] = (int16_t)stored_score;')]:
 if s.count(a)!=1: raise SystemExit(f'store write anchor {a!r} count={s.count(a)}')
 s=s.replace(a,b,1)

a='''    int slot = (int)(hash & TT_MASK);
    int base = slot * TT_BUCKETS;

    /* Check both buckets */'''
b='''    int slot = (int)(hash & TT_MASK);
    int base = slot * TT_BUCKETS;
    uint32_t key32 = (uint32_t)(hash >> 32);

    /* Check both buckets */'''
if s.count(a)!=1: raise SystemExit(f'probe anchor count={s.count(a)}')
s=s.replace(a,b,1)
a='if (TT_H[idx] != hash) continue;'
if s.count(a)!=1: raise SystemExit(f'probe compare count={s.count(a)}')
s=s.replace(a,'if (TT_H[idx] != key32) continue;',1)
p.write_text(s,encoding='utf-8')
print('applied v3.30 compact TT: 26 -> 15 bytes/entry across SoA fields')
