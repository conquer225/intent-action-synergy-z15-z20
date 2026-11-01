/* Synthetic, bounded H.264 test creation using existing board FFmpeg libraries. */
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/opt.h>
#include <stdio.h>
#include <stdlib.h>

static void fail(int code, const char *step) {
    if (code < 0) {
        char detail[256];
        av_strerror(code, detail, sizeof(detail));
        fprintf(stderr, "%s: %s\n", step, detail);
        exit(1);
    }
}

static void packets(AVCodecContext *codec, AVFormatContext *format,
                    AVStream *stream, AVPacket *packet) {
    for (;;) {
        int status = avcodec_receive_packet(codec, packet);
        if (status == AVERROR(EAGAIN) || status == AVERROR_EOF) return;
        fail(status, "receive_packet");
        if (!packet->duration) packet->duration = 1;
        av_packet_rescale_ts(packet, codec->time_base, stream->time_base);
        packet->stream_index = stream->index;
        fail(av_interleaved_write_frame(format, packet), "write_packet");
        av_packet_unref(packet);
    }
}

int main(int argc, char **argv) {
    if (argc != 5 && argc != 6) return 2;
    int width = atoi(argv[2]), height = atoi(argv[3]), bitrate = atoi(argv[4]);
    int frames = argc == 6 ? atoi(argv[5]) : 180;
    if (!((width == 1280 && height == 720) || (width == 1920 && height == 1080)) ||
        !(bitrate == 4000000 || bitrate == 8000000) ||
        !(frames == 60 || frames == 180)) return 2;
    const AVCodec *encoder = avcodec_find_encoder_by_name("libx264");
    if (!encoder) { fprintf(stderr, "Existing libx264 encoder unavailable\n"); return 1; }
    AVCodecContext *codec = avcodec_alloc_context3(encoder);
    AVFormatContext *format = NULL;
    fail(avformat_alloc_output_context2(&format, NULL, "mp4", argv[1]), "output_context");
    if (!codec || !format) return 1;
    codec->width = width;
    codec->height = height;
    codec->pix_fmt = AV_PIX_FMT_YUV420P;
    codec->time_base = (AVRational){1, 30};
    codec->framerate = (AVRational){30, 1};
    codec->gop_size = 30;
    codec->max_b_frames = 0;
    codec->bit_rate = bitrate;
    codec->rc_max_rate = bitrate;
    codec->rc_buffer_size = bitrate;
    codec->thread_count = 2;
    if (format->oformat->flags & AVFMT_GLOBALHEADER) codec->flags |= AV_CODEC_FLAG_GLOBAL_HEADER;
    fail(av_opt_set(codec->priv_data, "preset", "ultrafast", 0), "preset");
    fail(av_opt_set(codec->priv_data, "tune", "zerolatency", 0), "tune");
    fail(av_opt_set(codec->priv_data, "profile", "baseline", 0), "profile");
    fail(avcodec_open2(codec, encoder, NULL), "open_encoder");
    AVStream *stream = avformat_new_stream(format, NULL);
    if (!stream) return 1;
    stream->time_base = codec->time_base;
    stream->avg_frame_rate = codec->framerate;
    fail(avcodec_parameters_from_context(stream->codecpar, codec), "stream_parameters");
    fail(avio_open(&format->pb, argv[1], AVIO_FLAG_WRITE), "file_open");
    fail(avformat_write_header(format, NULL), "header");
    AVFrame *frame = av_frame_alloc();
    AVPacket *packet = av_packet_alloc();
    if (!frame || !packet) return 1;
    frame->format = codec->pix_fmt;
    frame->width = width;
    frame->height = height;
    fail(av_frame_get_buffer(frame, 32), "frame_buffer");
    for (int n = 0; n < frames; n++) {
        fail(av_frame_make_writable(frame), "writable_frame");
        for (int y = 0; y < height; y++)
            for (int x = 0; x < width; x++)
                frame->data[0][y * frame->linesize[0] + x] =
                    32 + ((x / 12 + y / 8 + n * 3) % 160) +
                    (((x / 80 + y / 80 + n / 15) % 2) ? 20 : 0);
        for (int y = 0; y < height / 2; y++)
            for (int x = 0; x < width / 2; x++) {
                frame->data[1][y * frame->linesize[1] + x] = 100 + (n % 30);
                frame->data[2][y * frame->linesize[2] + x] = 140 - (n % 30);
            }
        frame->pts = n;
        fail(avcodec_send_frame(codec, frame), "send_frame");
        packets(codec, format, stream, packet);
    }
    fail(avcodec_send_frame(codec, NULL), "flush_encoder");
    packets(codec, format, stream, packet);
    fail(av_write_trailer(format), "trailer");
    avio_closep(&format->pb);
    av_packet_free(&packet);
    av_frame_free(&frame);
    avcodec_free_context(&codec);
    avformat_free_context(format);
    printf("SYNTHETIC_H264_COMPLETE %dx%d frames=%d target_max_bps=%d\n", width, height, frames, bitrate);
    return 0;
}
