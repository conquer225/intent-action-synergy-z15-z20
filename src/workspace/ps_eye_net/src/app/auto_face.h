#ifndef AUTO_FACE_H
#define AUTO_FACE_H
#include "eye_tracker.h"
#include "haar.h"
typedef struct {
    EyeFaceBox face;
    EyeRoi left,right;
    int valid,faces,eye_count;
} Localization;
/* Trained face model followed by trained eye model, not proportional boxes. */
int auto_localize(const u8 *bgr,u32 stride,u32 width,u32 height,Localization *out);
int localization_near(const Localization *a,const Localization *b);
/* Carry calibration ROIs with the face-box transform. Eye boxes are a pose
 * check only: their common motion may include gaze and must not be subtracted.
 * Never use the dark-core center to estimate head motion. */
int localization_follow(const Localization *anchor,const Localization *current,
                        u32 width,u32 height,EyeRoi *left,EyeRoi *right);
#endif
