#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

int  small_nnue_load(const char *path);
int  small_nnue_ready(void);
int  small_nnue_evaluate(const uint8_t *board, int stm, int wk_sq, int bk_sq, uint64_t occ);
void small_nnue_destroy(void);

#ifdef __cplusplus
}
#endif
