#include <assert.h>
#include <stdio.h>
#include "../src/stream_liveness.h"

int main(void) {
    struct stream_liveness stream={.last_sample_ns=100};
    assert(stream_check(&stream,100)==STREAM_WAIT);
    assert(stream_check(&stream,100+999999999ull)==STREAM_WAIT);
    assert(stream_check(&stream,100+1000000000ull)==STREAM_RESUBSCRIBE);
    assert(stream.resubscribed);
    assert(stream_check(&stream,100+1500000000ull)==STREAM_WAIT);
    assert(stream_check(&stream,100+2999999999ull)==STREAM_WAIT);
    assert(stream_check(&stream,100+3000000000ull)==STREAM_EXPIRED);
    assert(stream_check(&stream,100+4000000000ull)==STREAM_EXPIRED);
    stream_received(&stream,100+2000000000ull);
    assert(!stream.resubscribed);
    assert(stream_check(&stream,100+2999999999ull)==STREAM_WAIT);
    assert(stream_check(&stream,100+3000000000ull)==STREAM_RESUBSCRIBE);
    assert(stream_check(&stream,stream.last_sample_ns-1)==STREAM_EXPIRED);
    stream_received(&stream,100+5000000000ull);
    assert(stream_check(&stream,100+8000000000ull)==STREAM_EXPIRED);
    assert(!stream.resubscribed);
    puts("stream_liveness: deadline, single retry, reset, and clock checks passed");
    return 0;
}
