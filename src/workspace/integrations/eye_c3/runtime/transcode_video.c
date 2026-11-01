/* Offline, video-only conversion using the board's existing FFmpeg libraries. */
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/opt.h>
#include <libswscale/swscale.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

static void check(int code, const char *step) {
    if (code < 0) {
        char message[256];
        av_strerror(code, message, sizeof(message));
        fprintf(stderr, "%s: %s\n", step, message);
        exit(1);
    }
}

static double seconds(void) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return now.tv_sec + now.tv_nsec / 1e9;
}

struct Conversion {
    AVFormatContext *output;
    AVCodecContext *encoder;
    AVStream *stream;
    AVPacket *packet;
    AVFrame *scaled;
    struct SwsContext *scale;
    AVRational source_time;
    double source_fps, origin, limit;
    int decoded, encoded, fps, origin_set;
};

static void write_packets(struct Conversion *work) {
    for (;;) {
        int result = avcodec_receive_packet(work->encoder, work->packet);
        if (result == AVERROR(EAGAIN) || result == AVERROR_EOF) return;
        check(result, "encoded_packet");
        if (!work->packet->duration) work->packet->duration = 1;
        av_packet_rescale_ts(work->packet, work->encoder->time_base,
                            work->stream->time_base);
        work->packet->stream_index = work->stream->index;
        check(av_interleaved_write_frame(work->output, work->packet), "write_packet");
        av_packet_unref(work->packet);
    }
}

static void convert_frame(struct Conversion *work, AVFrame *frame) {
    double timestamp = frame->best_effort_timestamp == AV_NOPTS_VALUE
        ? work->decoded / work->source_fps
        : frame->best_effort_timestamp * av_q2d(work->source_time);
    work->decoded++;
    if (!work->origin_set) {
        work->origin = timestamp;
        work->origin_set = 1;
    }
    timestamp -= work->origin;
    if (timestamp > work->limit) {
        fprintf(stderr, "Input exceeds this finite conversion trial\n");
        exit(1);
    }
    /* Temporal decimation, not duplicated or interpolated frames. */
    if (timestamp + 1e-6 < (double)work->encoded / work->fps) return;
    check(av_frame_make_writable(work->scaled), "writable_output");
    work->scale = sws_getCachedContext(work->scale, frame->width, frame->height,
        frame->format, work->encoder->width, work->encoder->height,
        AV_PIX_FMT_YUV420P, SWS_FAST_BILINEAR, NULL, NULL, NULL);
    if (!work->scale) exit(1);
    int rows = sws_scale(work->scale, (const uint8_t *const *)frame->data,
                        frame->linesize, 0, frame->height,
                        work->scaled->data, work->scaled->linesize);
    if (rows != work->encoder->height) exit(1);
    work->scaled->pts = work->encoded++;
    check(avcodec_send_frame(work->encoder, work->scaled), "encode_frame");
    write_packets(work);
}

static void drain(AVCodecContext *decoder, AVFrame *frame, struct Conversion *work) {
    for (;;) {
        int result = avcodec_receive_frame(decoder, frame);
        if (result == AVERROR(EAGAIN) || result == AVERROR_EOF) return;
        check(result, "decode_frame");
        convert_frame(work, frame);
        av_frame_unref(frame);
    }
}

int main(int argc, char **argv) {
    if (argc != 6 && argc != 7) return 2;
    int width = atoi(argv[3]), height = atoi(argv[4]), fps = atoi(argv[5]);
    int limit = argc == 7 ? atoi(argv[6]) : 15;
    if (limit < 1 || limit > 600) return 2;
    if (!((width == 1280 && height == 720) || (width == 640 && height == 360) ||
          (width == 288 && height == 512)) || (fps != 10 && fps != 20)) return 2;
    AVFormatContext *input = NULL;
    check(avformat_open_input(&input, argv[1], NULL, NULL), "open_input");
    check(avformat_find_stream_info(input, NULL), "stream_info");
    int index = av_find_best_stream(input, AVMEDIA_TYPE_VIDEO, -1, -1, NULL, 0);
    check(index, "video_stream");
    AVStream *source = input->streams[index];
    double source_fps = av_q2d(av_guess_frame_rate(input, source, NULL));
    if (source_fps < fps || source_fps > 240 ||
        source->codecpar->width > 4096 || source->codecpar->height > 4096) return 2;
    const AVCodec *decode_type = avcodec_find_decoder(source->codecpar->codec_id);
    const AVCodec *encode_type = avcodec_find_encoder_by_name("libx264");
    if (!decode_type || !encode_type) return 1;
    AVCodecContext *decoder = avcodec_alloc_context3(decode_type);
    AVCodecContext *encoder = avcodec_alloc_context3(encode_type);
    if (!decoder || !encoder) return 1;
    check(avcodec_parameters_to_context(decoder, source->codecpar), "parameters");
    decoder->thread_count = 2;
    check(avcodec_open2(decoder, decode_type, NULL), "open_decoder");
    struct Conversion work = {.encoder = encoder, .source_time = source->time_base,
        .source_fps = source_fps, .fps = fps, .limit = limit};
    check(avformat_alloc_output_context2(&work.output, NULL, "mp4", argv[2]), "output_context");
    if (!work.output) return 1;
    encoder->width = width;
    encoder->height = height;
    encoder->pix_fmt = AV_PIX_FMT_YUV420P;
    encoder->time_base = (AVRational){1, fps};
    encoder->framerate = (AVRational){fps, 1};
    encoder->gop_size = fps;
    encoder->max_b_frames = 0;
    encoder->bit_rate = width == 1280 ? 4000000 : 1000000;
    encoder->rc_max_rate = encoder->bit_rate;
    encoder->rc_buffer_size = encoder->bit_rate;
    encoder->thread_count = 2;
    if (work.output->oformat->flags & AVFMT_GLOBALHEADER)
        encoder->flags |= AV_CODEC_FLAG_GLOBAL_HEADER;
    check(av_opt_set(encoder->priv_data, "preset", "ultrafast", 0), "preset");
    check(av_opt_set(encoder->priv_data, "tune", "zerolatency", 0), "tune");
    check(av_opt_set(encoder->priv_data, "profile", "baseline", 0), "profile");
    check(avcodec_open2(encoder, encode_type, NULL), "open_encoder");
    work.stream = avformat_new_stream(work.output, NULL);
    if (!work.stream) return 1;
    work.stream->time_base = encoder->time_base;
    work.stream->avg_frame_rate = encoder->framerate;
    check(avcodec_parameters_from_context(work.stream->codecpar, encoder), "stream_parameters");
    int exclusive = open(argv[2], O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (exclusive < 0) { perror("exclusive_output"); return 1; }
    close(exclusive);
    check(avio_open(&work.output->pb, argv[2], AVIO_FLAG_WRITE), "open_output");
    check(avformat_write_header(work.output, NULL), "header");
    AVFrame *frame = av_frame_alloc();
    AVPacket *packet = av_packet_alloc();
    work.scaled = av_frame_alloc();
    work.packet = av_packet_alloc();
    if (!frame || !packet || !work.scaled || !work.packet) return 1;
    work.scaled->format = encoder->pix_fmt;
    work.scaled->width = width;
    work.scaled->height = height;
    check(av_frame_get_buffer(work.scaled, 32), "scaled_buffer");
    double start = seconds();
    int result;
    while ((result = av_read_frame(input, packet)) >= 0) {
        if (packet->stream_index == index) {
            check(avcodec_send_packet(decoder, packet), "decode_packet");
            drain(decoder, frame, &work);
        }
        av_packet_unref(packet);
    }
    if (result != AVERROR_EOF) check(result, "read_packet");
    check(avcodec_send_packet(decoder, NULL), "flush_decoder");
    drain(decoder, frame, &work);
    check(avcodec_send_frame(encoder, NULL), "flush_encoder");
    write_packets(&work);
    if (!work.encoded) return 1;
    check(av_write_trailer(work.output), "trailer");
    check(avio_closep(&work.output->pb), "close_output");
    printf("{\"source_codec\":\"%s\",\"source_profile\":%d,"
           "\"decoded_source_frames\":%d,\"encoded_frames\":%d,"
           "\"width\":%d,\"height\":%d,\"fps\":%d,\"wall_s\":%.6f,"
           "\"audio\":false,\"complete\":true}\n",
           avcodec_get_name(source->codecpar->codec_id), decoder->profile,
           work.decoded, work.encoded, width, height, fps, seconds() - start);
    sws_freeContext(work.scale);
    av_frame_free(&frame);
    av_frame_free(&work.scaled);
    av_packet_free(&packet);
    av_packet_free(&work.packet);
    avcodec_free_context(&decoder);
    avcodec_free_context(&encoder);
    avformat_close_input(&input);
    avformat_free_context(work.output);
    return 0;
}
