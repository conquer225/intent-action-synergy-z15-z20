/* Expand a prepared 640x360 BGR frame to the existing 720p scanout exactly. */
#include <arm_neon.h>
#include <stdint.h>
#include <string.h>

int expand_bgr_360(const uint8_t *source, uint8_t *destination, int stride) {
    if (!source || !destination || stride < 3840) return 0;
    for (int y = 0; y < 360; ++y) {
        const uint8_t *input = source + y * 1920;
        uint8_t *output = destination + y * 2 * stride;
        for (int x = 0; x < 640; x += 8) {
            uint8x8x3_t pixels = vld3_u8(input + x * 3), first, last;
            for (int channel = 0; channel < 3; ++channel) {
                uint8x8x2_t doubled = vzip_u8(pixels.val[channel], pixels.val[channel]);
                first.val[channel] = doubled.val[0];
                last.val[channel] = doubled.val[1];
            }
            vst3_u8(output + x * 6, first);
            vst3_u8(output + x * 6 + 24, last);
        }
        memcpy(output + stride, output, 3840);
    }
    return 1;
}
