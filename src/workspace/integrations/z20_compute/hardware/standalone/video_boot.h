#ifndef Z20_VIDEO_BOOT_H
#define Z20_VIDEO_BOOT_H
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    int (*camera)(void *, unsigned, unsigned, unsigned);
    int (*dma)(void *, unsigned, unsigned, unsigned, unsigned, unsigned);
    int (*display)(void *);
} z20_video_ops;
/* First-boot initialization only. Analysis must never call this on live video. */
int z20_video_start(const z20_video_ops *ops, void *context, unsigned base);
#ifdef __cplusplus
}
#endif
#endif
