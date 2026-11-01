#ifndef Z20_MLP_H
#define Z20_MLP_H
#include <stdint.h>
#define Z20_MAX_INPUTS 1024
#define Z20_HIDDEN 32
#define Z20_OUTPUTS 3
extern "C" int z20_mlp(const int8_t *input, const int8_t *w1, const int32_t *b1,
                       const int8_t *w2, const int32_t *b2, int32_t *output,
                       unsigned input_size, unsigned hidden_shift);
#endif
