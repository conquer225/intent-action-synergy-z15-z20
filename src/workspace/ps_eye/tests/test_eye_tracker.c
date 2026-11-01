#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "eye_tracker.h"
#include "hdmi_overlay.h"

#define W 160
#define H 80
#define STRIDE (W * 3)

static void frame_for(u8 *f, int lx, int rx)
{
    int x, y;
    memset(f, 160, STRIDE * H);
    for (y = 28; y < 36; ++y) for (x = lx - 4; x <= lx + 4; ++x) {
        f[y * STRIDE + x * 3 + 0] = 5; f[y * STRIDE + x * 3 + 1] = 5; f[y * STRIDE + x * 3 + 2] = 5;
    }
    for (y = 28; y < 36; ++y) for (x = rx - 4; x <= rx + 4; ++x) {
        f[y * STRIDE + x * 3 + 0] = 5; f[y * STRIDE + x * 3 + 1] = 5; f[y * STRIDE + x * 3 + 2] = 5;
    }
}

static void sample(EyeTracker *t, u8 *f, int lx, int rx, int n)
{
    int i;
    for (i = 0; i < n; ++i) { frame_for(f, lx, rx); eye_tracker_process(t, f, STRIDE, W, H, 100); }
}

int main(void)
{
    u8 *f = (u8 *)calloc(1, STRIDE * H);
    EyeRoi l = {10, 10, 60, 50, 24, 80}, r = {90, 10, 60, 50, 24, 80};
    EyeTracker t;
    if (!f) return 2;
    eye_tracker_init(&t, &l, &r);
    eye_tracker_start_calibration(&t);
    sample(&t, f, 20, 100, 36);
    sample(&t, f, 40, 120, 36);
    sample(&t, f, 60, 140, 36);
    if (t.calibration_mask != 7 || t.calibration_stage != 0) return 3;
    sample(&t, f, 20, 100, 9);
    if (t.event_seq != 1 || t.direction != EYE_DIR_LEFT) { printf("left fail seq=%lu dir=%d valid=%d cand=%d dwell=%lu nx=%d/%d\n", (unsigned long)t.event_seq, t.direction, t.valid, t.candidate, (unsigned long)t.dwell_ms, t.left.normalized_x, t.right.normalized_x); return 4; }
    t.commit = 0;
    sample(&t, f, 40, 120, 5);
    if (t.direction != EYE_DIR_CENTER || t.valid == 0) return 5;
    sample(&t, f, 60, 140, 9);
    if (t.event_seq != 2 || t.direction != EYE_DIR_RIGHT) return 6;
    frame_for(f, 20, 100);
    hdmi_overlay_apply(f, STRIDE, W, H, &t);
    if (f[0] == 160 || f[10 * STRIDE + 10 * 3] == 160) return 7;
    printf("eye_tracker host test passed: events=%lu\n", (unsigned long)t.event_seq);
    free(f);
    return 0;
}
