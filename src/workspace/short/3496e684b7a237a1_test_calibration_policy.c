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
