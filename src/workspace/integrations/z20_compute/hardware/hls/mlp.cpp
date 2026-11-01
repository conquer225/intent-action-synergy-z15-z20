#include "mlp.h"
#include <limits.h>

extern "C" int z20_mlp(const int8_t *input, const int8_t *w1, const int32_t *b1,
                       const int8_t *w2, const int32_t *b2, int32_t *output,
                       unsigned input_size, unsigned hidden_shift) {
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=samples depth=1024
#pragma HLS INTERFACE m_axi port=w1 offset=slave bundle=weights depth=32768
#pragma HLS INTERFACE m_axi port=b1 offset=slave bundle=weights depth=32
#pragma HLS INTERFACE m_axi port=w2 offset=slave bundle=weights depth=96
#pragma HLS INTERFACE m_axi port=b2 offset=slave bundle=weights depth=3
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=samples depth=3
#pragma HLS INTERFACE s_axilite port=input bundle=control
#pragma HLS INTERFACE s_axilite port=w1 bundle=control
#pragma HLS INTERFACE s_axilite port=b1 bundle=control
#pragma HLS INTERFACE s_axilite port=w2 bundle=control
#pragma HLS INTERFACE s_axilite port=b2 bundle=control
#pragma HLS INTERFACE s_axilite port=output bundle=control
#pragma HLS INTERFACE s_axilite port=input_size bundle=control
#pragma HLS INTERFACE s_axilite port=hidden_shift bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
    if (input_size < 1 || input_size > Z20_MAX_INPUTS || hidden_shift > 31) return 1;
    int8_t samples[Z20_MAX_INPUTS];
    int8_t hidden[Z20_HIDDEN];
    for (unsigned i = 0; i < input_size; ++i) {
#pragma HLS PIPELINE II=1
        samples[i] = input[i];
    }
    for (unsigned row = 0; row < Z20_HIDDEN; ++row) {
        int64_t sum = b1[row];
        for (unsigned i = 0; i < input_size; ++i) {
#pragma HLS PIPELINE II=1
            sum += (int32_t)samples[i] * (int32_t)w1[row * input_size + i];
        }
        if (sum < INT32_MIN || sum > INT32_MAX) return 2;
        // ReLU before scaling is equivalent for nonpositive values; avoid
        // implementation-defined signed right shifts and negative rounding.
        if (sum <= 0) hidden[row] = 0;
        else {
            if (hidden_shift) sum = (sum + ((int64_t)1 << (hidden_shift-1))) >> hidden_shift;
            hidden[row] = (int8_t)(sum > 127 ? 127 : sum);
        }
    }
    int32_t result[Z20_OUTPUTS];
    for (unsigned row = 0; row < Z20_OUTPUTS; ++row) {
        int64_t sum = b2[row];
        for (unsigned i = 0; i < Z20_HIDDEN; ++i) {
#pragma HLS PIPELINE II=1
            sum += (int32_t)hidden[i] * (int32_t)w2[row * Z20_HIDDEN + i];
        }
        if (sum < INT32_MIN || sum > INT32_MAX) return 2;
        result[row] = (int32_t)sum;
    }
    for (unsigned i = 0; i < Z20_OUTPUTS; ++i) output[i] = result[i];
    return 0;
}
