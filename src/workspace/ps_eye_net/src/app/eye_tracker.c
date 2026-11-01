#include "eye_tracker.h"

#define CAL_CORE_SPAN 24u
#define DWELL_LEFT_RIGHT_MS 750u
#define DWELL_CENTER_MS 350u
#define EYE_GRID_W 128u
#define EYE_GRID_H 96u
#define EYE_GRID_N (EYE_GRID_W*EYE_GRID_H)

/* Single workspace, like the Haar detector. The PC adapter serializes calls. */
static u8 eye_gray[EYE_GRID_N];
static u8 eye_input[EYE_GRID_N];
static u16 eye_labels[EYE_GRID_N], eye_queue[EYE_GRID_N];

static u8 gray_at(const u8 *p)
{ return (u8)((29u*p[0]+150u*p[1]+77u*p[2])>>8); }

static int median(int *values,unsigned n)
{
    for(unsigned i=1;i<n;i++) {
        int v=values[i];unsigned j=i;
        while(j && values[j-1]>v) { values[j]=values[j-1];j--; }
        values[j]=v;
    }
    return n%2?values[n/2]:(values[n/2-1]+values[n/2])/2;
}

static u32 percentile(const u32 *hist,u32 n,u32 percent)
{
    u32 target=(n*percent+99)/100,sum=0;
    for(u32 i=0;i<256;i++) { sum+=hist[i]; if(sum>=target) return i; }
    return 255;
}

int eye_analyze_rgb888(const u8 *frame,u32 stride,u32 width,u32 height,
                       const EyeRoi *roi,EyeFeature *out)
{
    u32 hist[256]={0},step=1,gw,gh,n;
    if(!out) return 0;
    *out=(EyeFeature){0};out->reason=EYE_FEATURE_ROI;
    if(!frame||!roi||!width||!height||width>4096||height>4096||stride<width*3u||stride>65536u||
       roi->w<8||roi->h<6||(u32)roi->x+roi->w>width||(u32)roi->y+roi->h>height) return 0;
    while((roi->w+step-1)/step>EYE_GRID_W||(roi->h+step-1)/step>EYE_GRID_H) step++;
    gw=(roi->w+step-1)/step;gh=(roi->h+step-1)/step;n=gw*gh;
    out->sample_count=(u16)n;out->min_gray=255;
    for(u32 y=0;y<gh;y++) for(u32 x=0;x<gw;x++) {
        u8 g=gray_at(frame+(roi->y+y*step)*stride+(roi->x+x*step)*3u);
        eye_input[y*gw+x]=g;
    }
    /* Remove isolated hot pixels and thin lash fragments before thresholding.
       Keep the raw image untouched and retain the existing geometry rejection. */
    for(u32 y=0;y<gh;y++) for(u32 x=0;x<gw;x++) {
        int v[9];unsigned count=0;
        for(int dy=-1;dy<=1;dy++) for(int dx=-1;dx<=1;dx++) {
            int xx=(int)x+dx,yy=(int)y+dy;
            if(xx<0) xx=0;
            if(yy<0) yy=0;
            if(xx>=(int)gw) xx=(int)gw-1;
            if(yy>=(int)gh) yy=(int)gh-1;
            v[count++]=eye_input[(u32)yy*gw+(u32)xx];
        }
        u8 g=(u8)median(v,9);
        eye_gray[y*gw+x]=g;hist[g]++;
        if(g<out->min_gray) out->min_gray=g;
        if(g>out->max_gray) out->max_gray=g;
    }
    /* Percentiles ignore isolated hot/dead pixels. The low tail selects a core
       without adding a fixed brightness offset to an underexposed image. */
    u32 low=percentile(hist,n,2),high=percentile(hist,n,90);
    out->contrast=(u8)(high-low);out->reason=EYE_FEATURE_CONTRAST;
    if(high<low+8u) return 0;
    u32 threshold=percentile(hist,n,20),cap=low+(high-low)/2u;
    if(threshold>cap) threshold=cap;
    out->threshold=(u8)threshold;
    for(u32 i=0;i<n;i++) {
        eye_labels[i]=eye_gray[i]<=threshold?1:0;
        if(eye_labels[i]) out->dark_count++;
    }
    out->reason=EYE_FEATURE_AREA;
    if(out->dark_count<6||out->dark_count*100u<n*2u||out->dark_count*100u>n*50u) return 0;
    u32 label=1,best=0,second=0,best_x=0,best_y=0,best_contrast=0;
    out->reason=EYE_FEATURE_SHAPE;
    for(u32 seed=0;seed<n;seed++) {
        if(eye_labels[seed]!=1) continue;
        label++;u32 head=0,tail=1,sx=0,sy=0,gsum=0;
        u32 xmin=gw,xmax=0,ymin=gh,ymax=0;
        eye_queue[0]=(u16)seed;eye_labels[seed]=(u16)label;
        while(head<tail) {
            u32 id=eye_queue[head++],x=id%gw,y=id/gw;
            sx+=x;sy+=y;gsum+=eye_gray[id];
            if(x<xmin) xmin=x;
            if(x>xmax) xmax=x;
            if(y<ymin) ymin=y;
            if(y>ymax) ymax=y;
            for(int dy=-1;dy<=1;dy++) for(int dx=-1;dx<=1;dx++) {
                int xx=(int)x+dx,yy=(int)y+dy;
                if(xx<0||yy<0||xx>=(int)gw||yy>=(int)gh) continue;
                u32 k=(u32)yy*gw+(u32)xx;
                if(eye_labels[k]==1) { eye_labels[k]=(u16)label;eye_queue[tail++]=(u16)k; }
            }
        }
        u32 bw=xmax-xmin+1,bh=ymax-ymin+1;
        /* Reject eyelid-like lines, fragmented noise, and border gradients. */
        if(tail<6||tail*100u<n*2u||bw<3||bh<3||bw>3*bh||bh>4*bw||
           tail*100u<bw*bh*40u||bw*100u>gw*85u||bh*100u>gh*95u||
           sx*100u<tail*gw*5u||sx*100u>tail*gw*95u||
           sy*100u<tail*gh*8u||sy*100u>tail*gh*92u) continue;
        int x0=(int)xmin-(int)(bw/3+1),x1=(int)xmax+(int)(bw/3+1);
        int y0=(int)ymin-(int)(bh/3+1),y1=(int)ymax+(int)(bh/3+1);
        u32 surround=0,surround_sum=0;
        for(int y=y0;y<=y1;y++) for(int x=x0;x<=x1;x++) {
            if(x<0||y<0||x>=(int)gw||y>=(int)gh) continue;
            u32 k=(u32)y*gw+(u32)x;
            if(eye_labels[k]!=(u16)label) { surround++;surround_sum+=eye_gray[k]; }
        }
        if(!surround||surround_sum/surround<gsum/tail+4u) continue;
        if(tail>best) { second=best;best=tail;best_x=sx;best_y=sy;best_contrast=surround_sum/surround-gsum/tail; }
        else if(tail>second) second=tail;
    }
    out->selected_count=(u16)best;
    if(!best) return 0;
    out->reason=EYE_FEATURE_AMBIGUOUS;
    if(second*100u>=best*60u||best*100u<out->dark_count*50u) return 0;
    out->x=(u16)(roi->x+(best_x*step+best/2)/best);
    out->y=(u16)(roi->y+(best_y*step+best/2)/best);
    /* Divide after normalization: rounded pixel crosshairs lose too much
       information in a 20-40 pixel wide eye. Widen before multiplying for
       large input ROIs; only two such divisions are needed per frame. */
    out->x_q8=roi->x*256u+(u32)(((u64)best_x*step*256u+best/2u)/best);
    out->y_q8=roi->y*256u+(u32)(((u64)best_y*step*256u+best/2u)/best);
    out->normalized_x=(u16)(((u64)best_x*step*256u+best*roi->w/2u)/(best*roi->w));
    out->confidence=(u8)(32u+(best_contrast>96u?96u:best_contrast));
    out->valid=1;out->reason=EYE_FEATURE_OK;return 1;
}

static void clear_gaze(EyeTracker *t)
{
    t->valid=0; t->commit=0; t->confidence=0;
    t->candidate=EYE_DIR_INVALID; t->direction=EYE_DIR_INVALID;
    t->dwell_ms=0;
    t->pending_direction=0;t->pending_count=0;t->pending_ms=0;
}
static void reset_filter(EyeTracker *t)
{ t->history_count=0;t->gaze_raw=0;t->gaze_filtered=0;t->tracking_reason=EYE_TRACK_WAIT; }
void eye_tracker_invalidate(EyeTracker *t)
{
    t->left=(EyeFeature){0}; t->right=(EyeFeature){0};
    clear_gaze(t);
    reset_filter(t);
}
void eye_tracker_pause(EyeTracker *t,u8 reason)
{
    eye_tracker_invalidate(t); t->calibration_paused=reason;
}
void eye_tracker_clear_calibration(EyeTracker *t)
{
    eye_tracker_invalidate(t); t->calibration_mask=0;
    t->calibration_stage=0; t->stage_ms=0; t->cal_failed=0; t->armed=1;
    t->calibration_stable=0; t->calibration_settle_ms=0; t->calibration_paused=0;
    t->cal_failure_reason=0;t->cal_failure_eye=0;t->cal_retry_stage=0;
    t->cal_failure_gap=0;t->cal_failure_noise=0;
    for(int e=0;e<2;e++) {
        t->calibration_ready[e]=0;t->calibration_core_span[e]=0;
        t->calibration_count[e]=0; t->calibration_outliers[e]=0;
        t->calibration_min[e]=0; t->calibration_max[e]=0; t->calibration_sum[e]=0;
        for(int i=0;i<3;i++) { t->calibration[e][i]=0;t->calibration_mad[e][i]=0; }
    }
}
void eye_tracker_init(EyeTracker *t,const EyeRoi *l,const EyeRoi *r)
{
    *t=(EyeTracker){0}; t->left_roi=*l; t->right_roi=*r; t->armed=1;
}
void eye_tracker_set_roi(EyeTracker *t,const EyeRoi *l,const EyeRoi *r)
{ t->left_roi=*l; t->right_roi=*r; }
void eye_tracker_set_face(EyeTracker *t,const EyeFaceBox *f)
{ t->face=f?*f:(EyeFaceBox){0}; }
void eye_tracker_start_calibration(EyeTracker *t)
{ eye_tracker_clear_calibration(t); t->calibration_stage=1; }
int eye_tracker_retry_calibration(EyeTracker *t)
{
    if(!t->cal_failed||t->cal_retry_stage<1||t->cal_retry_stage>3) return 0;
    u8 stage=t->cal_retry_stage;
    eye_tracker_invalidate(t);
    t->calibration_stage=stage;t->calibration_mask=(1u<<(stage-1))-1u;
    t->cal_failed=0;t->cal_failure_reason=0;t->cal_failure_eye=0;t->cal_retry_stage=0;
    t->cal_failure_gap=0;t->cal_failure_noise=0;
    t->stage_ms=0;t->calibration_settle_ms=0;t->calibration_stable=0;t->calibration_paused=0;
    for(int e=0;e<2;e++) {
        t->calibration_count[e]=0;t->calibration_ready[e]=0;t->calibration_core_span[e]=0;
        t->calibration_min[e]=0;t->calibration_max[e]=0;t->calibration_sum[e]=0;t->calibration_outliers[e]=0;
        for(int i=stage-1;i<3;i++) { t->calibration[e][i]=0;t->calibration_mad[e][i]=0; }
    }
    return 1;
}
static int distance(int a,int b) { return a>b?a-b:b-a; }
static int personal_position(const EyeTracker *t,const EyeFeature *f,int eye,int *value)
{
    int c=t->calibration[eye][1],l=(int)t->calibration[eye][0]-c;
    int r=(int)t->calibration[eye][2]-c,x=(int)f->normalized_x-c;
    if(!l||!r||l*r>=0) return 0;
    *value=x*l>0?-x*256/l:x*256/r;
    return *value>=-416 && *value<=416;
}
static u8 zone(int value)
{
    /* No guessed direction at the boundary between targets. */
    if(distance(value,-128)<24||distance(value,128)<24) return 0;
    return value<-128?EYE_DIR_LEFT:value>128?EYE_DIR_RIGHT:EYE_DIR_CENTER;
}
static int filtered_position(EyeTracker *t,int value,u32 dt)
{
    unsigned n=0;
    for(unsigned i=0;i<t->history_count;i++) {
        u32 age=t->history_age[i]+dt;
        if(age<=EYE_FILTER_WINDOW_MS) {
            t->history[n]=t->history[i];t->history_age[n++]=age;
        }
    }
    if(n==EYE_FILTER_SAMPLES) {
        for(unsigned i=1;i<n;i++) { t->history[i-1]=t->history[i];t->history_age[i-1]=t->history_age[i]; }
        n--;
    }
    t->history[n]=value;t->history_age[n]=0;t->history_count=(u8)(n+1);
    int sorted[EYE_FILTER_SAMPLES];
    for(unsigned i=0;i<=n;i++) sorted[i]=t->history[i];
    t->gaze_filtered=median(sorted,n+1);
    return n>=2;
}
static void fail_cal(EyeTracker *t,u8 reason,u8 eye,u8 stage,u16 gap,u16 noise)
{
    /* Keep the measurements and localization anchor available for diagnosis
       and explicit retry. Failed references can never drive an action. */
    clear_gaze(t);reset_filter(t);t->calibration_mask=0;t->cal_failed=1;
    t->cal_failure_reason=reason;t->cal_failure_eye=eye+1;t->cal_retry_stage=stage;
    t->cal_failure_gap=gap;t->cal_failure_noise=noise;
}
static void calibration_sample(EyeTracker *t,int e,const EyeFeature *f)
{
    if(!f->valid||t->calibration_ready[e]) return;
    u16 value=f->normalized_x;
    unsigned n=t->calibration_count[e];
    if(n==EYE_CAL_SAMPLES) {
        for(unsigned i=1;i<n;i++) t->calibration_samples[e][i-1]=t->calibration_samples[e][i];
        n--;
    }
    t->calibration_samples[e][n++]=value;t->calibration_count[e]=(u8)n;
    int values[EYE_CAL_SAMPLES];
    t->calibration_sum[e]=0;
    for(unsigned i=0;i<n;i++) { values[i]=t->calibration_samples[e][i];t->calibration_sum[e]+=values[i]; }
    (void)median(values,n);
    t->calibration_min[e]=(u16)values[0];t->calibration_max[e]=(u16)values[n-1];
    /* Ignore at most two extremes per tail for stability, not for the median
       or MAD. A bad first sample cannot poison the whole acquisition batch. */
    unsigned trim=n==EYE_CAL_SAMPLES?2u:0u;
    t->calibration_core_span[e]=(u16)(values[n-1-trim]-values[trim]);
    if(n==EYE_CAL_SAMPLES && t->calibration_core_span[e]<=CAL_CORE_SPAN) {
        t->calibration_ready[e]=1;
    }
}
void eye_tracker_process(EyeTracker *t,const u8 *frame,u32 stride,u32 width,u32 height,u32 dt)
{
    EyeFeature l={0},r={0};
    if(dt<=1000) {
        eye_analyze_rgb888(frame,stride,width,height,&t->left_roi,&l);
        eye_analyze_rgb888(frame,stride,width,height,&t->right_roi,&r);
    }
    eye_tracker_process_features(t,&l,&r,dt);
}
void eye_tracker_process_features(EyeTracker *t,const EyeFeature *left,const EyeFeature *right,u32 dt)
{
    t->commit=0; t->frame_count++; t->calibration_paused=0;
    /* A large observation gap is not continuous gaze. */
    if(dt>1000) {
        eye_tracker_pause(t,EYE_PAUSE_TIMING);
        return;
    }
    t->left=left?*left:(EyeFeature){0};
    t->right=right?*right:(EyeFeature){0};
    if(t->calibration_stage) {
        clear_gaze(t);
        t->calibration_paused=(!t->left.valid?EYE_PAUSE_LEFT:0)|(!t->right.valid?EYE_PAUSE_RIGHT:0);
        if(t->calibration_paused) t->invalid_count++;
        if(t->calibration_paused==3) return;
        if(t->stage_ms<3600000u) t->stage_ms+=dt;
        if(t->calibration_settle_ms<EYE_CAL_SETTLE_MS) {
            t->calibration_settle_ms+=dt;
            if(t->calibration_settle_ms>EYE_CAL_SETTLE_MS) t->calibration_settle_ms=EYE_CAL_SETTLE_MS;
            return;
        }
        calibration_sample(t,0,&t->left); calibration_sample(t,1,&t->right);
        t->calibration_stable=t->calibration_count[0]<t->calibration_count[1]?t->calibration_count[0]:t->calibration_count[1];
        if(t->calibration_ready[0] && t->calibration_ready[1]) {
            for(int e=0;e<2;e++) {
                int values[EYE_CAL_SAMPLES],dev[EYE_CAL_SAMPLES];
                for(unsigned i=0;i<EYE_CAL_SAMPLES;i++) values[i]=t->calibration_samples[e][i];
                int center=median(values,EYE_CAL_SAMPLES);
                for(unsigned i=0;i<EYE_CAL_SAMPLES;i++) dev[i]=distance(values[i],center);
                t->calibration[e][t->calibration_stage-1]=(u16)center;
                t->calibration_mad[e][t->calibration_stage-1]=(u16)median(dev,EYE_CAL_SAMPLES);
                t->calibration_count[e]=0; t->calibration_outliers[e]=0;t->calibration_ready[e]=0;
                t->calibration_core_span[e]=0;t->calibration_min[e]=0;t->calibration_max[e]=0;
            }
            t->calibration_mask |= 1u<<(t->calibration_stage-1);
            t->calibration_stage++; t->calibration_stable=0; t->calibration_settle_ms=0; t->stage_ms=0;
            if(t->calibration_stage>3) {
                t->calibration_stage=0;
                for(int e=0;e<2;e++) {
                    int a=(int)t->calibration[e][1]-t->calibration[e][0];
                    int b=(int)t->calibration[e][2]-t->calibration[e][1];
                    int noise_a=2*(t->calibration_mad[e][0]+t->calibration_mad[e][1]);
                    int noise_b=2*(t->calibration_mad[e][1]+t->calibration_mad[e][2]);
                    if(distance(a,0)<6) { fail_cal(t,EYE_CAL_SEPARATION,e,2,distance(a,0),noise_a);return; }
                    if(distance(b,0)<6) { fail_cal(t,EYE_CAL_SEPARATION,e,3,distance(b,0),noise_b);return; }
                    if(a*b<=0) { fail_cal(t,EYE_CAL_ORDER,e,2,0,0);return; }
                    if(distance(a,0)<=noise_a) {
                        u8 stage=t->calibration_mad[e][0]>t->calibration_mad[e][1]?1:2;
                        fail_cal(t,EYE_CAL_NOISE,e,stage,distance(a,0),noise_a);return;
                    }
                    if(distance(b,0)<=noise_b) {
                        u8 stage=t->calibration_mad[e][1]>t->calibration_mad[e][2]?2:3;
                        fail_cal(t,EYE_CAL_NOISE,e,stage,distance(b,0),noise_b);return;
                    }
                }
                reset_filter(t);
            }
        }
        return;
    }
    if(!t->left.valid||!t->right.valid) {
        t->invalid_count++; clear_gaze(t);reset_filter(t);t->tracking_reason=EYE_TRACK_FEATURE;return;
    }
    if(t->calibration_mask!=7) { clear_gaze(t);return; }
    if(!dt||dt>EYE_RUNTIME_GAP_MS) {
        clear_gaze(t);reset_filter(t);t->tracking_reason=EYE_TRACK_TIMING;return;
    }
    int l,r;
    if(!personal_position(t,&t->left,0,&l)||!personal_position(t,&t->right,1,&r)) {
        clear_gaze(t);reset_filter(t);t->tracking_reason=EYE_TRACK_RANGE;return;
    }
    /* Current measurements gate history; filtering must never conceal a
       lost eye, out-of-range observation or opposite binocular directions. */
    if(distance(l,r)>160 || (zone(l)&&zone(r)&&zone(l)!=zone(r))) {
        clear_gaze(t);reset_filter(t);t->tracking_reason=EYE_TRACK_DISAGREE;return;
    }
    t->gaze_raw=(l+r)/2;
    if(!filtered_position(t,t->gaze_raw,dt)) {
        clear_gaze(t);t->tracking_reason=EYE_TRACK_WAIT;return;
    }
    u8 dl=zone(t->gaze_filtered),raw=zone(t->gaze_raw);
    if(!dl||!raw) { clear_gaze(t);t->tracking_reason=EYE_TRACK_BOUNDARY;return; }
    if(raw!=dl) { clear_gaze(t);t->tracking_reason=EYE_TRACK_SWITCH;return; }
    if(t->pending_direction!=dl) {
        t->pending_direction=dl;t->pending_count=1;t->pending_ms=0;
    } else {
        if(t->pending_count<255) t->pending_count++;
        if(t->pending_ms<10000) t->pending_ms+=dt;
    }
    if(t->pending_count<2||t->pending_ms<80) {
        t->valid=0;t->commit=0;t->confidence=0;t->direction=0;t->candidate=0;t->dwell_ms=0;
        t->tracking_reason=EYE_TRACK_SWITCH;return;
    }
    t->valid=1; t->confidence=(t->left.confidence+t->right.confidence)/2;
    t->tracking_reason=EYE_TRACK_OK;
    t->candidate=dl;
    if(t->direction!=dl) { t->direction=dl; t->dwell_ms=0; }
    else if(t->dwell_ms<10000) t->dwell_ms+=dt;
    if(dl==EYE_DIR_CENTER && t->dwell_ms>=DWELL_CENTER_MS) t->armed=1;
    else if(dl!=EYE_DIR_CENTER && t->armed && t->dwell_ms>=DWELL_LEFT_RIGHT_MS) {
        t->event_seq++; t->commit=1; t->armed=0;
    }
}
const char *eye_direction_name(u8 d)
{
    switch(d) { case 1:return "LEFT"; case 2:return "CENTER"; case 3:return "RIGHT"; default:return "INVALID"; }
}
