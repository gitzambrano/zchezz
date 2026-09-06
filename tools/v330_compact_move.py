#!/usr/bin/env python3
from pathlib import Path

root=Path('engine/c/zchezz_v323')
main=root/'main.c'; s=main.read_text(encoding='utf-8')
old='#define ENGINE_VERSION "3.23"'
if s.count(old)!=1: raise SystemExit(f'version anchor count={s.count(old)}')
main.write_text(s.replace(old,'#define ENGINE_VERSION "3.30"',1),encoding='utf-8')

p=root/'board.h'; s=p.read_text(encoding='utf-8')
old='''typedef struct {
    uint8_t  from;
    uint8_t  to;
    uint8_t  prom;
    uint8_t  epc;
    uint8_t  castle;
    int32_t  score;
} Move;'''
new='''/* v3.30 experiment: compact identity fields while keeping the 32-bit
 * ordering score.  GCC/Clang layout is 8 bytes instead of 12. */
typedef struct {
    uint32_t from     : 6;
    uint32_t to       : 6;
    uint32_t prom     : 3;
    uint32_t epc      : 1;
    uint32_t castle   : 3;
    uint32_t reserved : 13;
    int32_t  score;
} Move;
_Static_assert(sizeof(Move) == 8, "v3.30 compact Move must be 8 bytes");'''
if s.count(old)!=1: raise SystemExit(f'Move anchor count={s.count(old)}')
p.write_text(s.replace(old,new,1),encoding='utf-8')
print('applied v3.30 compact Move')
