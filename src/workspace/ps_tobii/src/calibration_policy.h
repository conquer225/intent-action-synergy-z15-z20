/* Retry only a completed firmware OPERATION_FAILED response. A timeout leaves
 * command completion ambiguous, so never automatically resend it. */
#ifndef IS4_CALIBRATION_POLICY_H
#define IS4_CALIBRATION_POLICY_H
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define CALIBRATION_USB_CHUNK 8192
/* Each USB transfer has its own channel/length envelope. TTP header occurs
 * once, at offset zero in the reassembled body, even for a large model. */
static size_t calibration_out_chunk(unsigned char *out,const unsigned char *body,size_t len,size_t offset) {
    if(!out || !body || offset>=len)return 0;
    size_t n=len-offset;
    if(n>CALIBRATION_USB_CHUNK-8)n=CALIBRATION_USB_CHUNK-8;
    memset(out,0,4);
    out[4]=n&255;out[5]=(n>>8)&255;out[6]=(n>>16)&255;out[7]=(n>>24)&255;
    memcpy(out+8,body+offset,n);
    return n+8;
}
static uint32_t calibration_be32(const unsigned char *p) {
    return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static bool calibration_blob_valid(const unsigned char *p,uint32_t len,uint32_t capacity) {
    return p && len>=11 && len<=capacity && p[0]==0 && p[1]==0 && p[2]==21 &&
        calibration_be32(p+3)==len-7 && calibration_be32(p+7)==len-11;
}
static bool calibration_retry(int attempt, int limit, int error,
                              uint32_t status, bool stopping) {
    return !stopping && attempt < limit && error == -1 && status == 0x20000502;
}
#endif
