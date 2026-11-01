/* Offline audio cache preparation. Never opens a sound device or PL registers. */
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <libavutil/channel_layout.h>
#include <libswresample/swresample.h>
#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <sys/stat.h>
#include <unistd.h>

#define RATE 48000
#define CHANNELS 2
#define MAX_SAMPLES (RATE * 600LL)
#define MAX_FRAME_SAMPLES 262144

static double clock_seconds(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}

static int u32(FILE *f, uint32_t v) {
    unsigned char b[4] = {v & 255, (v >> 8) & 255, (v >> 16) & 255, (v >> 24) & 255};
    return fwrite(b, 1, 4, f) == 4 ? 0 : -1;
}

static int wav_header(FILE *f, uint32_t bytes) {
    if (fseek(f, 0, SEEK_SET) != 0) return -1;
    return fwrite("RIFF", 1, 4, f) != 4 || u32(f, 36 + bytes) ||
        fwrite("WAVEfmt ", 1, 8, f) != 8 || u32(f, 16) ||
        fwrite("\1\0\2\0", 1, 4, f) != 4 || u32(f, RATE) || u32(f, RATE * 4) ||
        fwrite("\4\0\20\0data", 1, 8, f) != 8 || u32(f, bytes) ? -1 : 0;
}

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "Usage: prepare_audio INPUT NEW_OUTPUT.wav (max 10 minutes)\n");
        return 2;
    }
    struct stat source;
    if (stat(argv[1], &source) || !S_ISREG(source.st_mode) || source.st_size <= 0 ||
            source.st_size > 512LL * 1024 * 1024) {
        fprintf(stderr, "Input must be a local regular file, at most 512 MiB\n");
        return 2;
    }
    AVFormatContext *format = NULL;
    AVCodecContext *codec = NULL;
    AVPacket *packet = NULL;
    AVFrame *frame = NULL;
    SwrContext *resampler = NULL;
    FILE *out = NULL;
    uint8_t *pcm = NULL;
    int rc = 1, output_created = 0, eof = 0, draining = 0, frames = 0, discontinuities = 0;
    int64_t samples = 0, layout = 0;
    double first = NAN, expected = NAN, start = clock_seconds();
    int stream = -1;
    if (avformat_open_input(&format, argv[1], NULL, NULL) < 0 ||
            avformat_find_stream_info(format, NULL) < 0) goto cleanup;
    stream = av_find_best_stream(format, AVMEDIA_TYPE_AUDIO, -1, -1, NULL, 0);
    if (stream == AVERROR_STREAM_NOT_FOUND) {
        puts("{\"audio_present\":false,\"audio_output\":false}");
        rc = 0;
        goto cleanup;
    }
    if (stream < 0) goto cleanup;
    const AVCodec *decoder = avcodec_find_decoder(format->streams[stream]->codecpar->codec_id);
    if (!decoder) goto cleanup;
    codec = avcodec_alloc_context3(decoder);
    if (!codec || avcodec_parameters_to_context(codec, format->streams[stream]->codecpar) < 0 ||
            avcodec_open2(codec, decoder, NULL) < 0 || codec->sample_rate <= 0 ||
            codec->channels < 1 || codec->channels > 8) goto cleanup;
    layout = codec->channel_layout ? (int64_t)codec->channel_layout : av_get_default_channel_layout(codec->channels);
    resampler = swr_alloc_set_opts(NULL, AV_CH_LAYOUT_STEREO, AV_SAMPLE_FMT_S16, RATE,
                                 layout, codec->sample_fmt, codec->sample_rate, 0, NULL);
    if (!resampler || swr_init(resampler) < 0) goto cleanup;
    packet = av_packet_alloc(); frame = av_frame_alloc();
    pcm = av_malloc(MAX_FRAME_SAMPLES * 4);
    if (!packet || !frame || !pcm) goto cleanup;
    int fd = open(argv[2], O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (fd < 0) { perror("new output"); goto cleanup; }
    output_created = 1;
    out = fdopen(fd, "wb");
    if (!out) { close(fd); goto cleanup; }
    if (wav_header(out, 0)) goto cleanup;
    while (!eof) {
        if (clock_seconds() - start > 180) { fprintf(stderr, "Preparation deadline exceeded\n"); goto cleanup; }
        int result = avcodec_receive_frame(codec, frame);
        if (result == AVERROR_EOF) { eof = 1; break; }
        if (result == 0) {
            if (frame->sample_rate != codec->sample_rate || frame->format != codec->sample_fmt ||
                    frame->channels != codec->channels || frame->nb_samples <= 0) goto cleanup;
            if (frame->best_effort_timestamp != AV_NOPTS_VALUE) {
                double pts = frame->best_effort_timestamp * av_q2d(format->streams[stream]->time_base);
                if (isnan(first)) first = pts;
                if (!isnan(expected) && fabs(pts - expected) > .05) discontinuities++;
                expected = pts + (double)frame->nb_samples / codec->sample_rate;
            }
            int capacity = swr_get_out_samples(resampler, frame->nb_samples);
            if (capacity < 0 || capacity > MAX_FRAME_SAMPLES) goto cleanup;
            int count = swr_convert(resampler, &pcm, capacity,
                                    (const uint8_t **)frame->extended_data, frame->nb_samples);
            if (count < 0 || samples + count > MAX_SAMPLES) goto cleanup;
            if (fwrite(pcm, 4, count, out) != (size_t)count) goto cleanup;
            samples += count; frames++; av_frame_unref(frame);
            continue;
        }
        if (result != AVERROR(EAGAIN) || draining) goto cleanup;
        do {
            av_packet_unref(packet);
            result = av_read_frame(format, packet);
        } while (result >= 0 && packet->stream_index != stream);
        if (result == AVERROR_EOF) {
            draining = 1; result = avcodec_send_packet(codec, NULL);
        } else if (result >= 0) {
            result = avcodec_send_packet(codec, packet);
        }
        if (result < 0) goto cleanup;
    }
    while (1) {
        int count = swr_convert(resampler, &pcm, MAX_FRAME_SAMPLES, NULL, 0);
        if (count < 0 || samples + count > MAX_SAMPLES) goto cleanup;
        if (!count) break;
        if (fwrite(pcm, 4, count, out) != (size_t)count) goto cleanup;
        samples += count;
    }
    if (!samples || discontinuities || wav_header(out, (uint32_t)(samples * 4)) || fflush(out)) {
        fprintf(stderr, "Empty audio, discontinuity or output error\n"); goto cleanup;
    }
    printf("{\"audio_present\":true,\"audio_output\":false,\"format\":\"pcm_s16le\","
           "\"sample_rate\":%d,\"channels\":%d,\"samples\":%lld,\"decoded_frames\":%d,"
           "\"duration_seconds\":%.6f,\"first_pts_seconds\":%.6f,\"timestamp_discontinuities\":%d,"
           "\"wall_seconds\":%.6f}\n", RATE, CHANNELS, (long long)samples, frames,
           (double)samples/RATE, isnan(first) ? 0 : first, discontinuities, clock_seconds()-start);
    rc = 0;
cleanup:
    if (out && fclose(out) != 0) rc = 1;
    if (rc && output_created) unlink(argv[2]);
    av_free(pcm); swr_free(&resampler); av_frame_free(&frame);
    av_packet_free(&packet); avcodec_free_context(&codec); avformat_close_input(&format);
    if (rc) fprintf(stderr, "Audio preparation failed; no playback attempted\n");
    return rc;
}
