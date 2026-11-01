#ifndef AUTO_VIDEO_IO_H
#define AUTO_VIDEO_IO_H
#include "xil_types.h"
#define VIDEO_W 1280u
#define VIDEO_H 720u
#define VIDEO_STRIDE (VIDEO_W*3u)
#define VIDEO_BYTES (VIDEO_STRIDE*VIDEO_H)
/* Cold startup includes the vendor PL capture's ten-frame warmup.
   Runtime still rejects a stopped stream within half a second. */
#define VIDEO_STARTUP_TIMEOUT_MS 3000u
#define VIDEO_FRAME_TIMEOUT_MS 500u
int video_init(void);
/* Park capture writer in another buffer, then copy the completed buffer. */
const u8 *video_snapshot(void);
/* r8 live path: health check only, no CPU display copy or buffer parking. */
int video_present(const u8 *image);
u32 video_now_ms(void);
u32 video_rx_status(void);
u32 video_tx_status(void);
u8 *video_work_frame(void);
#endif
