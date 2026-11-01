#include "net_control.h"
#include <string.h>
static const EyeRoi initial_l={300,240,260,160,24,80},initial_r={720,240,260,160,24,80};
void net_control_init(NetControl *c){memset(c,0,sizeof(*c));eye_tracker_init(&c->eye,&initial_l,&initial_r);}
void net_control_reset(NetControl *c){
    eye_tracker_clear_calibration(&c->eye);eye_tracker_set_face(&c->eye,0);
    c->last=(Localization){0};c->anchor=(Localization){0};c->stable=0;c->waiting=0;c->have_sample=0;
    c->crop_face=(EyeFaceBox){0};
}
int net_control_source(NetControl *c,int source){
    if(source!=NET_SOURCE_PC&&source!=NET_SOURCE_LOCAL)return 0;
    if(source==c->source)return 0;
    net_control_reset(c);c->source=source;return 1;
}
static int active(const NetControl *c){return c->eye.calibration_mask||c->eye.calibration_stage||c->eye.cal_failed;}
int net_control_crop(NetControl *c,const u8 *image,u32 stride,u32 width,u32 height,u32 sampled,u8 *pixels,NetFrame *out){
    if(!c)return 0;
    const EyeFaceBox *face=c->last.valid&&(u32)(sampled-c->last_result_ms)<1500u?&c->last.face:0;
    if(face){
        const NetFrame *p=&c->pending;
        u32 mx=face->w/16u,my=face->h/16u;
        u32 x1=(u32)p->x+p->w,y1=(u32)p->y+p->h;
        int retain=c->crop_face.valid&&!(p->flags&NET_SEARCH)&&p->camera_w==width&&p->camera_h==height&&
            face->x>=p->x&&face->y>=p->y&&(u32)face->x+face->w<=x1&&(u32)face->y+face->h<=y1&&
            face->x>=(p->x?p->x+mx:0)&&face->y>=(p->y?p->y+my:0)&&
            (u32)face->x+face->w<=x1-(x1<width?mx:0)&&
            (u32)face->y+face->h<=y1-(y1<height?my:0);
        if(!retain)c->crop_face=*face;
    }else c->crop_face=(EyeFaceBox){0};
    return net_crop(image,stride,width,height,c->crop_face.valid?&c->crop_face:0,pixels,out);
}
void net_control_begin(NetControl *c,const NetFrame *f,u32 session,u32 seq,u32 sampled){
    c->pending=*f;c->session=session;c->sequence=seq;c->sampled_ms=sampled;c->waiting=1;
}
static int roi_equal(const EyeRoi *a,const EyeRoi *b){return a->x==b->x&&a->y==b->y&&a->w==b->w&&a->h==b->h;}
static int roi_inside(const EyeRoi *r,u32 w,u32 h){return r->w>=8&&r->h>=6&&(u32)r->x+r->w<=w&&(u32)r->y+r->h<=h;}
static int feature(const NetEye *n,const EyeRoi *roi,EyeFeature *f){
    *f=(EyeFeature){0};f->reason=n->reason;
    if(!n->valid)return n->reason<=EYE_FEATURE_AMBIGUOUS;
    if(n->reason!=EYE_FEATURE_OK||n->contrast<8||n->quality<32||n->quality>128||!n->samples||
       n->samples>12288||n->selected<6||n->selected>n->samples||
       n->x_q8<roi->x*256u||n->y_q8<roi->y*256u||
       n->x_q8>=((u32)roi->x+roi->w)*256u||n->y_q8>=((u32)roi->y+roi->h)*256u)return 0;
    f->valid=1;f->x=(u16)((n->x_q8+128)/256);f->y=(u16)((n->y_q8+128)/256);
    /* Gaze stays relative to the face-projected original calibration ROI. */
    f->normalized_x=(u16)((n->x_q8-roi->x*256u+roi->w/2u)/roi->w);
    if(f->normalized_x>256)return 0;
    f->confidence=n->quality;f->contrast=n->contrast;f->selected_count=n->selected;f->sample_count=n->samples;
    f->dark_count=n->selected;f->x_q8=n->x_q8;f->y_q8=n->y_q8;return 1;
}
static void apply_localization(NetControl *c,const Localization *loc,int *ready,u8 *pause,u32 width,u32 height){
    if(!loc->valid){c->stable=0;eye_tracker_set_face(&c->eye,0);c->last=*loc;*ready=0;return;}
    if(active(c)&&!localization_follow(&c->anchor,loc,width,height,&c->eye.left_roi,&c->eye.right_roi)){
        c->stable=0;*ready=0;*pause=EYE_PAUSE_POSITION;
    }else{
        c->stable=localization_near(&c->last,loc)?c->stable+1:1;
        if(c->stable>3)c->stable=3;
        if(!active(c))eye_tracker_set_roi(&c->eye,&loc->left,&loc->right);
        *ready=c->stable>=2;
    }
    eye_tracker_set_face(&c->eye,&loc->face);c->last=*loc;
}
int net_control_result(NetControl *c,const NetPacket *p,u32 now){
    NetResult r;
    if(c->source!=NET_SOURCE_PC||!c->waiting||p->type!=NET_RESULT||p->session!=c->session||
       p->sequence!=c->sequence||p->sampled_ms!=c->sampled_ms||
       (u32)(now-c->sampled_ms)>NET_RESULT_TIMEOUT||!net_result_decode(p->payload,p->size,&r)){
        c->rejected++;return 0;
    }
    u32 w=c->pending.camera_w,h=c->pending.camera_h;
    Localization loc={0};EyeRoi l={0},rr={0};EyeFeature lf={0},rf={0};
    int pose_ok=1;
    if(r.flags){
        loc=(Localization){r.face,r.left.detected,r.right.detected,1,1,2};
        if(!r.face.valid||r.face.w<32||r.face.h<32||(u32)r.face.x+r.face.w>w||(u32)r.face.y+r.face.h>h||
           r.face.x<c->pending.x||r.face.y<c->pending.y||
           (u32)r.face.x+r.face.w>(u32)c->pending.x+c->pending.w||
           (u32)r.face.y+r.face.h>(u32)c->pending.y+c->pending.h||
           !roi_inside(&loc.left,w,h)||!roi_inside(&loc.right,w,h)||loc.left.x+loc.left.w>=loc.right.x||
           loc.left.x<r.face.x||loc.right.x+loc.right.w>r.face.x+r.face.w||
           loc.left.y<r.face.y||loc.right.y<r.face.y||loc.left.y+loc.left.h>r.face.y+r.face.h||loc.right.y+loc.right.h>r.face.y+r.face.h){
            c->rejected++;return 0;
        }
        l=loc.left;rr=loc.right;
        if(active(c))pose_ok=localization_follow(&c->anchor,&loc,w,h,&l,&rr);
        if(pose_ok&&(!roi_equal(&l,&r.left.analyzed)||!roi_equal(&rr,&r.right.analyzed)||
                     !feature(&r.left,&l,&lf)||!feature(&r.right,&rr,&rf))){c->rejected++;return 0;}
        /* Pose loss must report two invalid eyes; it can never inject a pupil. */
        if(!pose_ok&&(r.left.valid||r.right.valid)){c->rejected++;return 0;}
    }else if(r.left.valid||r.right.valid){c->rejected++;return 0;}
    c->waiting=0;c->accepted++;c->last_result_ms=now;
    c->period_ms=c->have_sample?(u32)(c->sampled_ms-c->last_sample_ms):0;
    c->last_sample_ms=c->sampled_ms;c->have_sample=1;c->detect_ms=r.process_ms;
    int ready=1;u8 pause=EYE_PAUSE_PAIR;
    apply_localization(c,&loc,&ready,&pause,w,h);
    if(ready&&pose_ok)eye_tracker_process_features(&c->eye,&lf,&rf,c->period_ms);
    else eye_tracker_pause(&c->eye,pause);
    return 1;
}
int net_control_timeout(NetControl *c,u32 now){
    if(!c->waiting||(u32)(now-c->sampled_ms)<=NET_RESULT_TIMEOUT)return 0;
    c->waiting=0;c->timeouts++;c->stable=0;eye_tracker_pause(&c->eye,EYE_PAUSE_TIMING);return 1;
}
int net_control_command(NetControl *c,char cmd,u32 now){
    if(cmd=='r'){net_control_reset(c);return 1;}
    if(cmd!='c'&&cmd!='t')return 0;
    if(c->stable<2||(!c->eye.left.valid&&!c->eye.right.valid)||
       (u32)(now-c->last_result_ms)>EYE_RUNTIME_GAP_MS)return 0;
    /* In-flight frames describe the old anchor/state and must be discarded. */
    if(cmd=='t'){
        if(!eye_tracker_retry_calibration(&c->eye))return 0;
    }else{c->anchor=c->last;eye_tracker_start_calibration(&c->eye);}
    c->waiting=0;c->have_sample=0;return 1;
}
void net_control_local(NetControl *c,const u8 *frame,u32 stride,u32 width,u32 height,const Localization *detected,u32 sampled,u32 elapsed){
    Localization loc=*detected;int ready=loc.valid;u8 pause=EYE_PAUSE_PAIR;
    c->period_ms=c->have_sample?(u32)(sampled-c->last_sample_ms):0;c->last_sample_ms=sampled;c->have_sample=1;
    c->last_result_ms=sampled+elapsed;c->detect_ms=elapsed;
    apply_localization(c,&loc,&ready,&pause,width,height);
    if(ready&&elapsed<=EYE_RUNTIME_GAP_MS)eye_tracker_process(&c->eye,frame,stride,width,height,c->period_ms);
    else eye_tracker_pause(&c->eye,elapsed>EYE_RUNTIME_GAP_MS?EYE_PAUSE_TIMING:pause);
}
