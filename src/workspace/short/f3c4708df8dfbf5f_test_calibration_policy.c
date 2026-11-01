#include <assert.h>
#include <stdlib.h>
#include "../src/calibration_policy.h"
int main(void) {
    uint32_t n=295205;
    unsigned char *blob=calloc(1,n);
    assert(blob);
    blob[2]=21;
    uint32_t outer=n-7,inner=n-11;
    for(int i=0;i<4;i++){blob[3+i]=(unsigned char)(outer>>(24-8*i));blob[7+i]=(unsigned char)(inner>>(24-8*i));}
    assert(!calibration_blob_valid(blob,n,4096));
    assert(calibration_blob_valid(blob,n,2*1024*1024-32));
    assert(!calibration_blob_valid(blob,n-1,2*1024*1024-32));
    assert(!calibration_blob_valid(blob,10,2*1024*1024-32));
    blob[2]=20;assert(!calibration_blob_valid(blob,n,2*1024*1024-32));
    assert(!calibration_blob_valid(NULL,n,2*1024*1024-32));
    unsigned char chunk[CALIBRATION_USB_CHUNK],*restored=malloc(n);
    assert(restored);
    for(size_t offset=0;offset<n;) {
        size_t bytes=calibration_out_chunk(chunk,blob,n,offset);
        assert(bytes>8 && bytes<=sizeof(chunk));
        assert(chunk[0]==0 && chunk[1]==0 && chunk[2]==0 && chunk[3]==0);
        uint32_t count=chunk[4]|((uint32_t)chunk[5]<<8)|((uint32_t)chunk[6]<<16)|((uint32_t)chunk[7]<<24);
        assert(count==bytes-8);
        memcpy(restored+offset,chunk+8,count);offset+=count;
    }
    assert(!memcmp(restored,blob,n));
    assert(!calibration_out_chunk(chunk,blob,n,n));
    assert(calibration_out_chunk(chunk,blob,8184,0)==8192);
    assert(calibration_out_chunk(chunk,blob,8185,8184)==9);
    free(restored);
    free(blob);
    assert(calibration_retry(1,3,-1,0x20000502,false));
    assert(calibration_retry(2,3,-1,0x20000502,false));
    assert(!calibration_retry(3,3,-1,0x20000502,false));
    assert(!calibration_retry(1,1,-1,0x20000502,false));
    assert(!calibration_retry(1,3,-1,0x20000502,true));
    assert(!calibration_retry(1,3,-7,0x20000502,false)); /* USB timeout */
    assert(!calibration_retry(1,3,-1,0,false)); /* USB IO failure */
    assert(!calibration_retry(1,3,-1,0x20000503,false)); /* malformed payload */
    assert(!calibration_retry(1,3,-1,0x20000508,false)); /* wrong state */
    assert(!calibration_retry(1,3,0,0x20000502,false)); /* no error */
    return 0;
}
