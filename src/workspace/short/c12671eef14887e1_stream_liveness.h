#ifndef STREAM_LIVENESS_H
#define STREAM_LIVENESS_H
#include <stdbool.h>
#include <stdint.h>

struct stream_liveness {
    uint64_t last_sample_ns;
    bool resubscribed;
};

enum stream_liveness_action { STREAM_WAIT, STREAM_RESUBSCRIBE, STREAM_EXPIRED };

static void stream_received(struct stream_liveness *stream, uint64_t now) {
    stream->last_sample_ns=now;
    stream->resubscribed=false;
}

static enum stream_liveness_action stream_check(struct stream_liveness *stream, uint64_t now) {
    if(now<stream->last_sample_ns)return STREAM_EXPIRED;
    uint64_t gap=now-stream->last_sample_ns;
    if(gap>=3000000000ull)return STREAM_EXPIRED;
    if(gap>=1000000000ull && !stream->resubscribed) {
        stream->resubscribed=true;
        return STREAM_RESUBSCRIBE;
    }
    return STREAM_WAIT;
}
#endif
