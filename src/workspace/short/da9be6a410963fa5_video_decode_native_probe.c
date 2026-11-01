/* Decode synthetic H.264 to memory; never accesses PL or a display device. */
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/imgutils.h>
#include <libswscale/swscale.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>

static double seconds(clockid_t clock) {
    struct timespec now;
    if (clock_gettime(clock, &now)) exit(1);
    return now.tv_sec + now.tv_nsec / 1e9;
}

static void check(int status, const char *step) {
    if (status < 0) {
        char error[256];
        av_strerror(status, error, sizeof(error));
        fprintf(stderr, "%s: %s\n", step, error);
        exit(1);
    }
}

struct Output {
    struct SwsContext *convert;
    uint8_t *planes[4];
    int strides[4];
    int frames;
    uint64_t checksum;
};

static void drain(AVCodecContext *codec, AVFrame *frame, struct Output *output) {
    for (;;) {
        int status = avcodec_receive_frame(codec, frame);
        if (status == AVERROR(EAGAIN) || status == AVERROR_EOF) return;
        check(status, "receive_frame");
        if (output->convert) {
            int rows = sws_scale(output->convert, (const uint8_t *const *)frame->data,
                                 frame->linesize, 0, frame->height,
                                 output->planes, output->strides);
            if (rows != frame->height) exit(1);
            output->checksum += output->planes[0][0];
        } else {
            output->checksum += frame->data[0][0];
        }
        output->frames++;
        av_frame_unref(frame);
    }
}

int main(int argc, char **argv) {
    if (argc != 4 || (strcmp(argv[2], "yuv") && strcmp(argv[2], "bgr"))) return 2;
    int threads = atoi(argv[3]);
    if (threads != 1 && threads != 2) return 2;
    AVFormatContext *format = NULL;
    check(avformat_open_input(&format, argv[1], NULL, NULL), "open_input");
    check(avformat_find_stream_info(format, NULL), "stream_info");
    int index = av_find_best_stream(format, AVMEDIA_TYPE_VIDEO, -1, -1, NULL, 0);
    check(index, "video_stream");
    AVStream *stream = format->streams[index];
    const AVCodec *decoder = avcodec_find_decoder(stream->codecpar->codec_id);
    if (!decoder) return 1;
    AVCodecContext *codec = avcodec_alloc_context3(decoder);
    if (!codec) return 1;
    check(avcodec_parameters_to_context(codec, stream->codecpar), "parameters");
    codec->thread_count = threads;
    check(avcodec_open2(codec, decoder, NULL), "open_decoder");
    AVFrame *frame = av_frame_alloc();
    AVPacket *packet = av_packet_alloc();
    if (!frame || !packet) return 1;
    struct Output output = {0};
    if (!strcmp(argv[2], "bgr")) {
        output.convert = sws_getContext(codec->width, codec->height, codec->pix_fmt,
                                        codec->width, codec->height, AV_PIX_FMT_BGR24,
                                        SWS_FAST_BILINEAR, NULL, NULL, NULL);
        if (!output.convert) return 1;
        check(av_image_alloc(output.planes, output.strides, codec->width,
                             codec->height, AV_PIX_FMT_BGR24, 32), "image_alloc");
    }
    double cpu_start = seconds(CLOCK_PROCESS_CPUTIME_ID);
    double start = seconds(CLOCK_MONOTONIC);
    int status, timed_out = 0;
    while ((status = av_read_frame(format, packet)) >= 0) {
        if (packet->stream_index == index) {
            check(avcodec_send_packet(codec, packet), "send_packet");
            drain(codec, frame, &output);
        }
        av_packet_unref(packet);
        if (seconds(CLOCK_MONOTONIC) - start > 20) {
            timed_out = 1;
            break;
        }
    }
    if (!timed_out) {
        if (status != AVERROR_EOF) check(status, "read_frame");
        check(avcodec_send_packet(codec, NULL), "flush_decoder");
        drain(codec, frame, &output);
    }
    double elapsed = seconds(CLOCK_MONOTONIC) - start;
    double cpu = seconds(CLOCK_PROCESS_CPUTIME_ID) - cpu_start;
    struct rusage usage;
    if (!output.frames || getrusage(RUSAGE_SELF, &usage)) return 1;
    printf("{\"mode\":\"%s\",\"threads\":%d,\"width\":%d,\"height\":%d,"
           "\"codec_profile\":%d,\"expected_frames\":%" PRId64 ",\"frames\":%d,"
           "\"complete\":%s,\"wall_s\":%.6f,\"decoded_fps\":%.6f,"
           "\"process_cpu_percent\":%.3f,\"peak_rss_mib\":%.3f,"
           "\"checksum\":%" PRIu64 ",\"output\":\"memory only, not HDMI\"}\n",
           argv[2], threads, codec->width, codec->height, codec->profile,
           stream->nb_frames, output.frames,
           !timed_out && output.frames == stream->nb_frames ? "true" : "false",
           elapsed, output.frames / elapsed, cpu / elapsed * 100,
           usage.ru_maxrss / 1024.0, output.checksum);
    av_freep(&output.planes[0]);
    sws_freeContext(output.convert);
    av_packet_free(&packet);
    av_frame_free(&frame);
    avcodec_free_context(&codec);
    avformat_close_input(&format);
    return 0;
}
