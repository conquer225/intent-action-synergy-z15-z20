#ifndef LIVE_OSD_H
#define LIVE_OSD_H
#include "eye_tracker.h"
int live_osd_init(void);
int live_osd_publish(const EyeTracker *tracker,u32 source_seq,u32 source_ms,int auto_mode);
int live_osd_clear(void);
u32 live_osd_display_frames(void);
u32 live_osd_camera_frames(void);
#endif
