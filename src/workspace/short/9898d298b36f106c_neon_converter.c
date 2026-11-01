/* Fixed 720p, limited-range BT.601 YUV420 -> BGR. No MMIO or owned buffers. */
#include <arm_neon.h>
#include <stdint.h>
#include <string.h>

static uint8x8_t channel(int32x4_t low, int32x4_t high) {
    return vqmovun_s16(vcombine_s16(vqrshrn_n_s32(low, 8), vqrshrn_n_s32(high, 8)));
}

static int16x8_t chroma(const uint8_t *source) {
    uint32_t four;
    memcpy(&four, source, sizeof(four));
    uint8x8_t packed = vreinterpret_u8_u64(vcreate_u64(four));
    uint8x8_t twice = vzip_u8(packed, packed).val[0];
    return vsubq_s16(vreinterpretq_s16_u16(vmovl_u8(twice)), vdupq_n_s16(128));
}

int neon_bgr_convert(const uint8_t *source, uint8_t *destination, int stride) {
    if (!source || !destination || stride < 3840) return 0;
    const uint8_t *u_plane = source + 921600;
    const uint8_t *v_plane = source + 1152000;
    for (int y = 0; y < 720; ++y) {
        const uint8_t *luma = source + y * 1280;
        const uint8_t *u = u_plane + (y / 2) * 640;
        const uint8_t *v = v_plane + (y / 2) * 640;
        uint8_t *output = destination + y * stride;
        for (int x = 0; x < 1280; x += 8) {
            int16x8_t yy = vsubq_s16(vreinterpretq_s16_u16(vmovl_u8(vld1_u8(luma+x))),
                                    vdupq_n_s16(16));
            int16x8_t uu = chroma(u+x/2), vv = chroma(v+x/2);
            int32x4_t yl = vmull_n_s16(vget_low_s16(yy), 298);
            int32x4_t yh = vmull_n_s16(vget_high_s16(yy), 298);
            uint8x8x3_t bgr;
            bgr.val[0] = channel(vmlal_n_s16(yl, vget_low_s16(uu), 516),
                                 vmlal_n_s16(yh, vget_high_s16(uu), 516));
            bgr.val[1] = channel(vmlsl_n_s16(vmlsl_n_s16(yl, vget_low_s16(uu), 100),
                                            vget_low_s16(vv), 208),
                                 vmlsl_n_s16(vmlsl_n_s16(yh, vget_high_s16(uu), 100),
                                            vget_high_s16(vv), 208));
            bgr.val[2] = channel(vmlal_n_s16(yl, vget_low_s16(vv), 409),
                                 vmlal_n_s16(yh, vget_high_s16(vv), 409));
            vst3_u8(output + x * 3, bgr);
        }
    }
    return 1;
}
