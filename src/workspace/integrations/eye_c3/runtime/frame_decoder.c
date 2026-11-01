/* Decode directly into a caller-owned BGR frame; no MMIO or allocation ownership. */
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libswscale/swscale.h>
#include <libavutil/display.h>
#include <math.h>
#include <stdlib.h>

struct Reader {
    AVFormatContext *format;
    AVCodecContext *codec;
    AVPacket *packet;
    AVFrame *frame;
    struct SwsContext *scale;
    int stream, flushing;
};

void video_close(struct Reader *reader) {
    if (!reader) return;
    sws_freeContext(reader->scale);
    av_frame_free(&reader->frame);
    av_packet_free(&reader->packet);
    avcodec_free_context(&reader->codec);
    avformat_close_input(&reader->format);
    free(reader);
}

struct Reader *video_open(const char *path, int threads) {
    if (threads < 1 || threads > 2) return NULL;
    struct Reader *reader = calloc(1, sizeof(*reader));
    if (!reader) return NULL;
    if (avformat_open_input(&reader->format, path, NULL, NULL) < 0 ||
        avformat_find_stream_info(reader->format, NULL) < 0) goto failure;
    reader->stream = av_find_best_stream(reader->format, AVMEDIA_TYPE_VIDEO, -1, -1, NULL, 0);
    if (reader->stream < 0) goto failure;
    AVCodecParameters *parameters = reader->format->streams[reader->stream]->codecpar;
    if (parameters->width <= 0 || parameters->height <= 0 ||
        parameters->width > 4096 || parameters->height > 4096) goto failure;
    const AVCodec *type = avcodec_find_decoder(parameters->codec_id);
    if (!type) goto failure;
    reader->codec = avcodec_alloc_context3(type);
    if (!reader->codec || avcodec_parameters_to_context(reader->codec, parameters) < 0)
        goto failure;
    reader->codec->thread_count = threads;
    if (avcodec_open2(reader->codec, type, NULL) < 0) goto failure;
    reader->packet = av_packet_alloc();
    reader->frame = av_frame_alloc();
    if (!reader->packet || !reader->frame) goto failure;
    return reader;
failure:
    video_close(reader);
    return NULL;
}

double video_fps(struct Reader *reader) {
    return av_q2d(av_guess_frame_rate(reader->format,
                  reader->format->streams[reader->stream], NULL));
}

int video_width(struct Reader *reader) {return reader->codec->width;}
int video_height(struct Reader *reader) {return reader->codec->height;}
double video_aspect(struct Reader *reader) {
    AVRational sar=reader->format->streams[reader->stream]->sample_aspect_ratio;
    return sar.num>0 && sar.den>0 ? av_q2d(sar) : 1.;
}
int video_rotation(struct Reader *reader) {
    int size=0;
    uint8_t *data=av_stream_get_side_data(reader->format->streams[reader->stream],AV_PKT_DATA_DISPLAYMATRIX,&size);
    if (!data || size<9*(int)sizeof(int32_t))return 0;
    double angle=-av_display_rotation_get((const int32_t *)data);
    if (!isfinite(angle))return -1;
    int rounded=(int)lround(angle);
    if (fabs(angle-rounded)>.05)return -1;
    rounded=(rounded%360+360)%360;
    return rounded%90==0 ? rounded : -1;
}

int video_rewind(struct Reader *reader) {
    AVStream *stream = reader->format->streams[reader->stream];
    int64_t start = stream->start_time == AV_NOPTS_VALUE ? 0 : stream->start_time;
    int result = av_seek_frame(reader->format, reader->stream, start, AVSEEK_FLAG_BACKWARD);
    if (result < 0) return result;
    avcodec_flush_buffers(reader->codec);
    av_packet_unref(reader->packet);
    av_frame_unref(reader->frame);
    reader->flushing = 0;
    return 0;
}

static int next_frame(struct Reader *reader) {
    for (;;) {
        int result = avcodec_receive_frame(reader->codec, reader->frame);
        if (result == AVERROR_EOF) return 0;
        if (result == 0) {
            return 1;
        }
        if (result != AVERROR(EAGAIN) || reader->flushing) return result;
        do {
            result = av_read_frame(reader->format, reader->packet);
            if (result < 0) break;
            if (reader->packet->stream_index == reader->stream) break;
            av_packet_unref(reader->packet);
        } while (1);
        if (result == AVERROR_EOF) {
            reader->flushing = 1;
            result = avcodec_send_packet(reader->codec, NULL);
        } else if (result >= 0) {
            result = avcodec_send_packet(reader->codec, reader->packet);
            av_packet_unref(reader->packet);
        }
        if (result < 0) return result;
    }
}

int video_read_to(struct Reader *reader, unsigned char *destination,
                  int width, int height, int stride) {
    if (!reader || !destination || width <= 0 || height <= 0 ||
        width > 1920 || height > 1080 || stride < width * 3) return AVERROR(EINVAL);
    int result = next_frame(reader);
    if (result != 1) return result;
    AVFrame *frame = reader->frame;
    reader->scale = sws_getCachedContext(reader->scale, frame->width, frame->height,
        frame->format, width, height, AV_PIX_FMT_BGR24,
        SWS_FAST_BILINEAR, NULL, NULL, NULL);
    if (!reader->scale) return AVERROR(ENOMEM);
    uint8_t *planes[4] = {destination, NULL, NULL, NULL};
    int strides[4] = {stride, 0, 0, 0};
    int rows = sws_scale(reader->scale, (const uint8_t *const *)frame->data,
        frame->linesize, 0, frame->height, planes, strides);
    av_frame_unref(frame);
    return rows == height ? 1 : AVERROR(EIO);
}

/* Prepared cache uses planar YUV420: half the BGR storage/bandwidth. */
int video_read_yuv(struct Reader *reader, unsigned char *destination, int width, int height) {
    if (!reader || !destination || width != 1280 || height != 720) return AVERROR(EINVAL);
    int result = next_frame(reader);
    if (result != 1) return result;
    AVFrame *frame = reader->frame;
    reader->scale = sws_getCachedContext(reader->scale, frame->width, frame->height,
        frame->format, width, height, AV_PIX_FMT_YUV420P,
        SWS_FAST_BILINEAR, NULL, NULL, NULL);
    if (!reader->scale) return AVERROR(ENOMEM);
    int pixels = width * height;
    uint8_t *planes[4] = {destination, destination + pixels,
                          destination + pixels * 5 / 4, NULL};
    int strides[4] = {width, width / 2, width / 2, 0};
    int rows = sws_scale(reader->scale, (const uint8_t *const *)frame->data,
                        frame->linesize, 0, frame->height, planes, strides);
    av_frame_unref(frame);
    return rows == height ? 1 : AVERROR(EIO);
}

struct SwsContext *bgr_open(void) {
    return sws_getContext(1280, 720, AV_PIX_FMT_YUV420P, 1280, 720, AV_PIX_FMT_BGR24,
                         SWS_FAST_BILINEAR, NULL, NULL, NULL);
}

int bgr_convert(struct SwsContext *scale, const unsigned char *source,
                unsigned char *destination, int stride) {
    if (!scale || !source || !destination || stride < 3840) return AVERROR(EINVAL);
    const uint8_t *planes[4] = {source, source + 921600, source + 1152000, NULL};
    int strides[4] = {1280, 640, 640, 0};
    uint8_t *output[4] = {destination, NULL, NULL, NULL};
    int output_strides[4] = {stride, 0, 0, 0};
    return sws_scale(scale, planes, strides, 0, 720, output, output_strides) == 720
        ? 1 : AVERROR(EIO);
}

void bgr_close(struct SwsContext *scale) { sws_freeContext(scale); }
