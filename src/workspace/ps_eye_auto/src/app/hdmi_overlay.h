#ifndef PS_EYE_HDMI_OVERLAY_H
#define PS_EYE_HDMI_OVERLAY_H

#include "xil_types.h"
#include "eye_tracker.h"

/* Draws a small status bar, ROI borders and feature markers into a B,G,R frame. */
void hdmi_overlay_apply(u8 *frame, u32 stride, u32 width, u32 height,
                        const EyeTracker *tracker);

#endif
