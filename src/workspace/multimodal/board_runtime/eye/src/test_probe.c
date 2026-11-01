/* Real capture decoding and framing regressions; compile next to generated C. */
#define main probe_entry_not_run
#include "is4-probe.c"
#undef main
#include <assert.h>

int main(int argc, char **argv) {
    assert(argc == 2);
    FILE *file = fopen(argv[1], "rb");
    assert(file != NULL);
    unsigned char raw[4096];
    size_t len = fread(raw, 1, sizeof(raw), file);
    assert(!ferror(file) && feof(file) && len > 0);
    fclose(file);
    struct gaze_sample sample;
    assert(decode_gaze_sample(raw, (uint32_t)len, &sample));
    assert(sample.has_gaze_2d && sample.gaze_valid == 0);
    assert(sample.validity_l == 4 && sample.validity_r == 4);
    for (size_t i = 0; i < len; i++)
        assert(!decode_gaze_sample(raw, (uint32_t)i, &sample));

    struct parser *parser = calloc(1, sizeof(*parser));
    struct ttp_frame *frame = calloc(1, sizeof(*frame));
    assert(parser && frame);
    unsigned char ttp[8192], wire[8192];
    size_t tlen = build_frame(ttp, 77, STREAM_GAZE, raw, len);
    put_be32(ttp, TTP_MAGIC_NOTIFY);
    size_t wlen = wrap_envelope(wire, ttp, tlen);
    wire[0] = 1;
    /* Fragmentation at every wire boundary without added envelopes. */
    for (size_t split = 1; split < wlen; split++) {
        parser->len = 0;
        assert(parser_feed(parser, wire, split) == 0);
        assert(parser_pop(parser, frame) == 0);
        assert(parser_feed(parser, wire + split, wlen - split) == 0);
        assert(parser_pop(parser, frame) == 1);
        assert(frame->plen == len && frame->seq == 77 && frame->op == STREAM_GAZE);
        assert(memcmp(frame->payload, raw, len) == 0);
        assert(parser_pop(parser, frame) == 0);
    }
    /* The repeated USB envelope observed while a large image is incomplete. */
    parser->len = 0;
    assert(parser_feed(parser, wire, 100) == 0);
    unsigned char continuation[8192] = {1, 0, 0, 0};
    put_le32(continuation + 4, (uint32_t)(wlen - 100));
    memcpy(continuation + 8, wire + 100, wlen - 100);
    assert(parser_feed(parser, continuation, wlen - 100 + 8) == 0);
    assert(parser_pop(parser, frame) == 1);
    assert(memcmp(frame->payload, raw, len) == 0);
    /* Coalesced notifications must both be recovered. */
    parser->len = 0;
    assert(parser_feed(parser, wire, wlen) == 0);
    assert(parser_feed(parser, wire, wlen) == 0);
    assert(parser_pop(parser, frame) == 1);
    assert(parser_pop(parser, frame) == 1);
    assert(parser_pop(parser, frame) == 0);
    /* Untrusted payload lengths cannot overrun the bounded accumulator. */
    parser->len = 0;
    put_be32(wire + ENVELOPE_SIZE + 20, MAX_FRAME_BYTES);
    assert(parser_feed(parser, wire, 32) == 0);
    assert(parser_pop(parser, frame) < 0);
    free(frame);
    free(parser);
    puts("PASS: actual IS4 sample, all payload truncations, wire fragmentation, repeated envelopes, coalesced frames, oversized frame rejection");
    return 0;
}
