/* Decode audio into codec-owned RAM only. No ALSA, device opens or sound output. */
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <stdio.h>
#include <math.h>
#include <time.h>

static double now(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    AVFormatContext *f = NULL;
    AVCodecContext *codec = NULL;
    AVPacket *packet = NULL;
    AVFrame *frame = NULL;
    int exit_code = 1, frames = 0, discontinuities = 0, complete = 0;
    long long samples = 0;
    double first = NAN, end = NAN, start = now();
    if (avformat_open_input(&f, argv[1], NULL, NULL) < 0 ||
        avformat_find_stream_info(f, NULL) < 0) goto cleanup;
    int stream = av_find_best_stream(f, AVMEDIA_TYPE_AUDIO, -1, -1, NULL, 0);
    if (stream < 0) {
        printf("{\"audio_present\":false,\"silent\":true,\"audio_output\":false}\n");
        exit_code = 0; goto cleanup;
    }
    AVCodecParameters *parameters = f->streams[stream]->codecpar;
    const AVCodec *decoder = avcodec_find_decoder(parameters->codec_id);
    if (!decoder) goto cleanup;
    codec = avcodec_alloc_context3(decoder);
    if (!codec || avcodec_parameters_to_context(codec, parameters) < 0 ||
        avcodec_open2(codec, decoder, NULL) < 0) goto cleanup;
    packet = av_packet_alloc(); frame = av_frame_alloc();
    if (!packet || !frame) goto cleanup;
    int draining = 0;
    while (now() - start < 60 && samples < 48000LL * 3600) {
        int result = avcodec_receive_frame(codec, frame);
        if (result == AVERROR_EOF) { complete = 1; break; }
        if (result == 0) {
            if (frame->sample_rate <= 0) goto cleanup;
            double pts = frame->best_effort_timestamp == AV_NOPTS_VALUE ? NAN :
                frame->best_effort_timestamp * av_q2d(f->streams[stream]->time_base);
            double duration = (double)frame->nb_samples / frame->sample_rate;
            if (!isnan(pts)) {
                if (isnan(first)) first = pts;
                if (!isnan(end) && fabs(pts - end) > .1) discontinuities++;
                end = pts + duration;
            }
            samples += frame->nb_samples; frames++;
            av_frame_unref(frame); continue;
        }
        if (result != AVERROR(EAGAIN) || draining) goto cleanup;
        do {
            result = av_read_frame(f, packet);
            if (result < 0 || packet->stream_index == stream) break;
            av_packet_unref(packet);
        } while (1);
        if (result == AVERROR_EOF) {
            draining = 1; result = avcodec_send_packet(codec, NULL);
        } else if (result >= 0) {
            result = avcodec_send_packet(codec, packet); av_packet_unref(packet);
        }
        if (result < 0) goto cleanup;
    }
    printf("{\"audio_present\":true,\"audio_output\":false,\"silent\":true,"
           "\"codec_id\":%d,\"sample_rate\":%d,\"channels\":%d,"
           "\"decoded_frames\":%d,\"decoded_samples\":%lld,\"complete\":%s,"
           "\"timestamp_discontinuities\":%d,\"timestamp_span_s\":%.6f,"
           "\"decoded_seconds\":%.6f,\"wall_s\":%.6f}\n",
           parameters->codec_id, codec->sample_rate, codec->channels, frames, samples,
           complete?"true":"false",discontinuities, isnan(end-first)?-1:end-first,
           codec->sample_rate ? (double)samples/codec->sample_rate : 0, now()-start);
    exit_code = frames > 0 ? 0 : 1;
cleanup:
    av_frame_free(&frame); av_packet_free(&packet);
    avcodec_free_context(&codec); avformat_close_input(&f);
    return exit_code;
}
