/* IS4 board worker. Reuses the credited, generated USB framing/decoder only. */
#define main diagnostic_probe_main
#include "is4-probe.c"
#undef main
#include <poll.h>
#include <unistd.h>
#include <math.h>
#include <sys/file.h>
#include <fcntl.h>
#include "calibration_policy.h"
#include "direction_policy.h"

static struct parser parser;
static struct ttp_frame reply;
static libusb_device_handle *device;
static uint32_t sequence;
static FILE *samples;
static int valid_count, sample_count;
#define CALIBRATION_MAX_BYTES (MAX_FRAME_BYTES-TTP_HDR_SIZE-ENVELOPE_SIZE)
static unsigned char backup[CALIBRATION_MAX_BYTES];
static uint32_t backup_len;
static unsigned char display_backup[MAX_PACKET_BYTES];
static uint32_t display_backup_len;
static bool display_changed;
static uint64_t session_start;
static uint64_t next_image;
static int image_index, detected_left,detected_right,detected_both;
static int detected_pupil_left,detected_pupil_right;
static uint32_t failure_status;
static bool entered, applied, keep_model;
static const char *sample_label="calibration";
static uint64_t quality_started;
static int quality_samples,quality_left,quality_right,quality_pupil_left,quality_pupil_right,quality_distance_n;
static double quality_distance_sum;
static bool validation_stream;
static bool selection_test, selection_stream;
static int calibration_points=9;
static bool direction_mode,direction_trained;
static int direction_collect=-1,direction_n[3];
static uint64_t direction_first[3],direction_last[3];
static double direction_data[3][512],direction_anchor[3],direction_mad[3];
static double direction_normalize(double x) {
    return direction_x(direction_anchor,x);
}
static int target_index=-1;
static double target_x,target_y;
static char target_label[32];
static uint64_t next_gaze_event,last_gaze_ns,max_gaze_gap_ns;
static int target_samples[9],target_valid[9],target_correct[9];
static double target_error_sum[9];

static void notify_sample(struct ttp_frame *frame) {
    if(frame->magic==TTP_MAGIC_NOTIFY && frame->op==STREAM_IMAGE_SECONDARY) {
        uint64_t now=monotonic_ns();
        struct image_frame image;
        if(now>=next_image && decode_image_payload(frame->op,frame->payload,frame->plen,&image)) {
            char path[1024];
            if(!write_pgm_frame(".",&image,image_index,image_index%2,true,path,sizeof(path))) {
                next_image=now+1000000000ull;image_index++;
                fprintf(stderr,"private_ir_frame monotonic_ns=%llu path=%s\n",(unsigned long long)now,path);
            }
        }
        return;
    }
    if (frame->magic != TTP_MAGIC_NOTIFY || frame->op != STREAM_GAZE) return;
    struct gaze_sample g;
    if (!decode_gaze_sample(frame->payload, frame->plen, &g)) return;
    sample_count++;
    quality_samples++;
    bool left=g.eye_present_l==1,right=g.eye_present_r==1;
    quality_left+=left;quality_right+=right;
    quality_pupil_left+=left && g.has_pupil_l && isfinite(g.pupil_l_mm) && g.pupil_l_mm>0;
    quality_pupil_right+=right && g.has_pupil_r && isfinite(g.pupil_r_mm) && g.pupil_r_mm>0;
    if(left && g.has_left_origin && isfinite(g.eye_l_z) && g.eye_l_z>0) {
        quality_distance_sum+=g.eye_l_z;quality_distance_n++;
    }
    if(right && g.has_right_origin && isfinite(g.eye_r_z) && g.eye_r_z>0) {
        quality_distance_sum+=g.eye_r_z;quality_distance_n++;
    }
    uint64_t quality_now=monotonic_ns();
    if(!quality_started)quality_started=quality_now;
    if(quality_now-quality_started>=500000000ull) {
        char distance[64];
        if(quality_distance_n)snprintf(distance,sizeof(distance),"%.1f",quality_distance_sum/quality_distance_n);
        else snprintf(distance,sizeof(distance),"null");
        printf("{\"kind\":\"quality\",\"samples\":%d,\"left\":%d,\"right\":%d,\"pupil_left\":%d,\"pupil_right\":%d,\"distance_mm\":%s}\n",quality_samples,quality_left,quality_right,quality_pupil_left,quality_pupil_right,distance);
        quality_started=quality_now;quality_samples=quality_left=quality_right=quality_pupil_left=quality_pupil_right=quality_distance_n=0;
        quality_distance_sum=0;
    }
    detected_left+=g.eye_present_l==1;detected_right+=g.eye_present_r==1;
    detected_both+=g.eye_present_l==1 && g.eye_present_r==1;
    detected_pupil_left+=left && g.has_pupil_l && isfinite(g.pupil_l_mm) && g.pupil_l_mm>0;
    detected_pupil_right+=right && g.has_pupil_r && isfinite(g.pupil_r_mm) && g.pupil_r_mm>0;
    bool valid = g.gaze_valid == 1 && g.has_gaze_2d && isfinite(g.gaze_x) &&
        (direction_mode || (isfinite(g.gaze_y) && g.gaze_x >= 0 && g.gaze_x <= 1 &&
        g.gaze_y >= 0 && g.gaze_y <= 1)) &&
        ((g.eye_present_l == 1 && g.validity_l == 0) ||
         (g.eye_present_r == 1 && g.validity_r == 0));
    if (valid) valid_count++;
    if(direction_mode && valid && direction_collect>=0) {
        int i=direction_collect;
        if(direction_n[i]<512) {
            uint64_t now=monotonic_ns();
            if(!direction_n[i])direction_first[i]=now;
            direction_last[i]=now;
            direction_data[i][direction_n[i]++]=g.gaze_x;
        }
    }
    if(selection_stream) {
        uint64_t now=monotonic_ns();
        if(direction_mode) {
            const char *kind=direction_trained?"horizontal_gaze":"direction_gaze";
            double x=direction_trained?direction_normalize(g.gaze_x):g.gaze_x;
            if(valid)printf("{\"kind\":\"%s\",\"valid\":true,\"x\":%.6f,\"monotonic_ns\":%llu}\n",kind,x,(unsigned long long)now);
            else printf("{\"kind\":\"%s\",\"valid\":false,\"monotonic_ns\":%llu}\n",kind,(unsigned long long)now);
        }
        else if(valid)printf("{\"kind\":\"gaze\",\"valid\":true,\"x\":%.6f,\"y\":%.6f,\"monotonic_ns\":%llu}\n",g.gaze_x,g.gaze_y,(unsigned long long)now);
        else printf("{\"kind\":\"gaze\",\"valid\":false,\"monotonic_ns\":%llu}\n",(unsigned long long)now);
    }
    if(validation_stream) {
        uint64_t now=monotonic_ns();
        if(last_gaze_ns && now-last_gaze_ns>max_gaze_gap_ns)max_gaze_gap_ns=now-last_gaze_ns;
        last_gaze_ns=now;
        if(target_index>=0) {
            target_samples[target_index]++;
            if(valid) {
                target_valid[target_index]++;
                target_correct[target_index]+=(g.gaze_x<1.0/3?0:g.gaze_x<2.0/3?1:2)==(int)(target_x*3);
                target_error_sum[target_index]+=hypot(g.gaze_x-target_x,g.gaze_y-target_y);
            }
        }
        if(now>=next_gaze_event) {
            if(valid)printf("{\"kind\":\"gaze\",\"valid\":true,\"x\":%.6f,\"y\":%.6f}\n",g.gaze_x,g.gaze_y);
            else puts("{\"kind\":\"gaze\",\"valid\":false}");
            next_gaze_event=now+100000000ull;
        }
    }
    if (samples) { write_csv_sample(samples,sample_label,session_start,monotonic_ns(),sample_count,frame,&g); fflush(samples); }
}

static int request(uint32_t op, const unsigned char *payload, size_t len, int ms) {
    failure_status=0;
    if (len > CALIBRATION_MAX_BYTES) return -1;
    unsigned char *packet=malloc(ENVELOPE_SIZE+TTP_HDR_SIZE+len);
    if(!packet)return LIBUSB_ERROR_NO_MEM;
    uint32_t seq = sequence++;
    uint64_t request_start=monotonic_ns();
    size_t n = build_frame(packet+ENVELOPE_SIZE, seq, op, payload, len);
    memset(packet,0,4);put_le32(packet+4,(uint32_t)n);
    int err=0;
    if(ENVELOPE_SIZE+n<=CALIBRATION_USB_CHUNK)err=send_packet(device,packet,ENVELOPE_SIZE+n);
    else {
        unsigned char chunk[CALIBRATION_USB_CHUNK];
        for(size_t offset=0;offset<n && !err;) {
            if(stop_requested){err=LIBUSB_ERROR_INTERRUPTED;break;}
            size_t bytes=calibration_out_chunk(chunk,packet+ENVELOPE_SIZE,n,offset);
            int transferred=0;
            err=libusb_bulk_transfer(device,TOBII_EP_OUT,chunk,(int)bytes,&transferred,2000);
            if(!err && transferred!=(int)bytes)err=LIBUSB_ERROR_IO;
            if(err){fprintf(stderr,"large_send_failed op=%04x offset=%zu bytes=%zu transferred=%d error=%d\n",op,offset,bytes,transferred,err);break;}
            offset+=bytes-ENVELOPE_SIZE;
            /* Keep incoming images/gaze draining while writing a large blob.
             * Parser sees each actual IN transfer, preserving envelope boundaries. */
            uint64_t drain_until=monotonic_ns()+20000000ull;
            while(monotonic_ns()<drain_until && offset<n) {
                unsigned char incoming[READ_BUFFER_BYTES];int received=0;
                int rc=libusb_bulk_transfer(device,TOBII_EP_IN,incoming,sizeof(incoming),&received,1);
                if(received>0 && parser_feed(&parser,incoming,received)){err=LIBUSB_ERROR_OVERFLOW;break;}
                int popped;
                while((popped=parser_pop(&parser,&reply))>0)notify_sample(&reply);
                if(popped<0){err=LIBUSB_ERROR_OTHER;break;}
                if(rc && rc!=LIBUSB_ERROR_TIMEOUT){err=rc;break;}
                if(!received)break;
            }
        }
        fprintf(stderr,"large_send op=%04x body_bytes=%zu error=%d\n",op,n,err);
    }
    free(packet);
    if (err) {fprintf(stderr,"command_send_failed op=%04x bytes=%zu error=%d\n",op,ENVELOPE_SIZE+n,err);return err;}
    uint64_t until = monotonic_ns()+(uint64_t)ms*1000000ull;
    while (!stop_requested && monotonic_ns()<until) {
        int rc=read_next_frame(device,&parser,&reply,100);
        if (rc<0) {fprintf(stderr,"command_read_failed op=%04x error=%d\n",op,rc);return rc;}
        if (!rc) continue;
        notify_sample(&reply);
        if (reply.magic!=TTP_MAGIC_RSP || reply.seq!=seq || reply.op!=op) continue;
        fprintf(stderr,"command op=%04x seq=%u header8=%08x status=%08x bytes=%u elapsed_ms=%.3f start_ns=%llu\n",
                op,seq,reply.header8,reply.status,reply.plen,(monotonic_ns()-request_start)/1e6,(unsigned long long)request_start);
        if (reply.status) {failure_status=reply.status;return -1;}
        return 0;
    }
    return LIBUSB_ERROR_TIMEOUT;
}

static bool blob_valid(const unsigned char *p, uint32_t len) {
    return calibration_blob_valid(p,len,sizeof(backup));
}
static int save(const char *name,const unsigned char *p,size_t len) {
    FILE *f=fopen(name,"wb");
    if (!f) return -1;
    bool ok=fwrite(p,1,len,f)==len;
    if (fflush(f) || fsync(fileno(f))) ok=false;
    if (fclose(f)) ok=false;
    return ok?0:-1;
}
static int read_model(const char *received_name) {
    int err=request(0x044c,NULL,0,4000);
    if(err)return err;
    if (save(received_name,reply.payload,reply.plen))return -1;
    if(!blob_valid(reply.payload,reply.plen)) {
        fprintf(stderr,"calibration_blob_invalid bytes=%u capacity=%zu prefix=%02x%02x%02x\n",reply.plen,sizeof(backup),reply.payload[0],reply.payload[1],reply.payload[2]);
        return -1;
    }
    return 0;
}
static int ensure_model(const char *path,bool functional_validation) {
    if(read_model("calibration_received_before.bin"))return -1;
    backup_len=reply.plen;memcpy(backup,reply.payload,backup_len);
    if(save("calibration_before.bin",backup,backup_len))return -1;
    FILE *file=fopen(path,"rb");
    if(!file)return -1;
    unsigned char *desired=malloc(CALIBRATION_MAX_BYTES);
    if(!desired){fclose(file);return -1;}
    size_t n=fread(desired,1,CALIBRATION_MAX_BYTES,file);
    bool valid=calibration_blob_valid(desired,n,CALIBRATION_MAX_BYTES) && fgetc(file)==EOF && !ferror(file);
    fclose(file);
    if(!valid){free(desired);return -1;}
    bool same=n==backup_len && !memcmp(desired,backup,n);
    int err=0;
    if(!same) {
        applied=true; /* A lost upload response still requires restoring the backup. */
        err=request(0x0456,desired,n,10000);
    }
    if(!err)err=read_model("calibration_received_restored.bin");
    bool identical=!err && reply.plen==n && !memcmp(reply.payload,desired,n);
    /* A nonidentical readback is never a verified restore. Only an explicit
     * independent human validation may examine this accepted candidate. */
    if(!err && !identical && (!functional_validation || reply.plen!=n || n<4096))err=-1;
    free(desired);
    if(err)return err;
    keep_model=identical;
    printf("{\"kind\":\"model\",\"byte_identical\":%s,\"functional_pending\":%s,\"uploaded\":%s,\"bytes\":%zu}\n",identical?"true":"false",identical?"false":"true",same?"false":"true",n);
    return 0;
}
static int validate_tracking(void) {
    sample_label="transition";validation_stream=true;
    puts("{\"kind\":\"ready\"}");
    int next=0;
    uint64_t deadline=monotonic_ns()+240000000000ull;
    while(!stop_requested && monotonic_ns()<deadline) {
        struct pollfd in={STDIN_FILENO,POLLIN,0};
        if(poll(&in,1,0)>0) {
            char line[128];int index;double x,y;
            if(!(in.revents&POLLIN) || !fgets(line,sizeof(line),stdin))return -1;
            if(!strcmp(line,"transition\n")) {
                target_index=-1;sample_label="transition";
            } else if(sscanf(line,"target %d %lf %lf",&index,&x,&y)==3) {
                if(index!=next || index>=9 || !isfinite(x)||!isfinite(y)||x<0||x>=1||y<0||y>=1)return -1;
                target_index=index;target_x=x;target_y=y;next++;
                snprintf(target_label,sizeof(target_label),"validation_%d",index);sample_label=target_label;
                fprintf(stderr,"validation_target index=%d x=%.6f y=%.6f monotonic_ns=%llu\n",index,x,y,(unsigned long long)monotonic_ns());
            } else if(!strcmp(line,"finish\n") && next==9) {
                target_index=-1;sample_label="after_validation";validation_stream=false;
                if(read_model("calibration_received_after_validation.bin"))return -1;
                /* Compare against the verified intended model, even after a reboot restore. */
                FILE *f=fopen("calibration_received_restored.bin","rb");if(!f)return -1;
                unsigned char *verified=malloc(sizeof(backup));if(!verified){fclose(f);return -1;}
                size_t n=fread(verified,1,sizeof(backup),f);bool ok=!ferror(f)&&fgetc(f)==EOF;fclose(f);
                bool unchanged=ok && reply.plen==n && !memcmp(reply.payload,verified,n);free(verified);
                if(!unchanged)return -1;
                bool passed=max_gaze_gap_ns<=250000000ull;
                for(int i=0;i<9;i++)passed=passed && target_samples[i]>=300 && target_valid[i]>=.9*target_samples[i] && target_correct[i]>=.9*target_valid[i];
                int total=0,valid_total=0;
                bool baseline=max_gaze_gap_ns<=250000000ull;
                for(int i=0;i<9;i++) {
                    total+=target_samples[i];valid_total+=target_valid[i];
                    baseline=baseline && target_samples[i]>=300 && target_valid[i]>=30 && target_correct[i]>=.9*target_valid[i];
                }
                baseline=baseline && total>0 && valid_total>=.9*total;
                /* User accepted overall 90%+ as a baseline. Preserve strict
                 * per-hold assessment separately; never turn it into a strict pass. */
                if(applied)keep_model=baseline;
                printf("{\"kind\":\"result\",\"validation\":true,\"unchanged\":true,\"strict\":%s,\"baseline\":%s,\"retained\":%s,\"max_gap_ms\":%.3f,\"points\":[",passed?"true":"false",baseline?"true":"false",keep_model?"true":"false",max_gaze_gap_ns/1e6);
                for(int i=0;i<9;i++)printf("%s{\"samples\":%d,\"valid\":%d,\"correct\":%d,\"mean_error_norm\":%.6f}",i?",":"",target_samples[i],target_valid[i],target_correct[i],target_valid[i]?target_error_sum[i]/target_valid[i]:-1);
                puts("]}");return 0;
            } else return -1;
        }
        int rc=read_next_frame(device,&parser,&reply,50);
        if(rc<0)return rc;
        if(rc)notify_sample(&reply);
    }
    return -1;
}
static int begin(void) {
    /* Vendor serialization: start/stop/clear/retrieve/apply have NO payload. */
    if(!selection_test) {
        if(read_model("calibration_received_before.bin"))return -1;
        backup_len=reply.plen; memcpy(backup,reply.payload,backup_len);
        if (save("calibration_before.bin",backup,backup_len)) return -1;
    }
    entered=true; /* A timed-out start may still have reached the device. */
    if (request(0x03f2,NULL,0,2000)) return -1;
    applied=true; /* Clear may affect active calibration on some firmware. */
    if (request(0x0424,NULL,0,2000)) return -1;
    return 0;
}
static int tracking_check(void) {
    /* Compare tracking around calibration mode without clear/add/apply. */
    if(read_model("calibration_received_before.bin"))return -1;
    backup_len=reply.plen;memcpy(backup,reply.payload,backup_len);
    if(save("calibration_before.bin",backup,backup_len))return -1;
    const char *stages[]={"baseline","calibration_mode","after_exit"};
    for(int stage=0;stage<3;stage++) {
        if(stage==1) {
            entered=true;
            applied=true; /* Preserve the backup even on cancel or a lost reply. */
            if(request(0x03f2,NULL,0,2000))return -1;
        } else if(stage==2) {
            if(request(0x03fc,NULL,0,2000))return -1;
            entered=false;
        }
        printf("{\"kind\":\"stage\",\"stage\":\"%s\"}\n",stages[stage]);
        fprintf(stderr,"tracking_stage stage=%s start_ms=%.3f\n",stages[stage],(monotonic_ns()-session_start)/1e6);
        int before=sample_count,l=detected_left,r=detected_right,b=detected_both;
        uint64_t until=monotonic_ns()+5000000000ull;
        while(!stop_requested && monotonic_ns()<until) {
            int rc=read_next_frame(device,&parser,&reply,100);
            if(rc<0)return rc;
            if(rc)notify_sample(&reply);
        }
        fprintf(stderr,"tracking_check stage=%s samples=%d left=%d right=%d both=%d\n",stages[stage],sample_count-before,detected_left-l,detected_right-r,detected_both-b);
        if(stop_requested)return -1;
    }
    if(read_model("calibration_received_after_check.bin"))return -1;
    bool unchanged=reply.plen==backup_len && !memcmp(reply.payload,backup,backup_len);
    if(!unchanged){applied=true;return -1;} /* Restore if this firmware changed it. */
    applied=false;
    puts("{\"kind\":\"result\",\"diagnostic\":true,\"unchanged\":true}");
    return 0;
}
static int compute(void) {
    applied=true; /* Preserve rollback even if the apply reply is lost. */
    if (request(0x042e,NULL,0,18000)) return -1;
    if (request(0x03fc,NULL,0,2000)) return -1;
    entered=false;
    bool changed=false;
    if(!selection_test) {
        if(read_model("calibration_received.bin"))return -1;
        changed=reply.plen!=backup_len || memcmp(reply.payload,backup,backup_len)!=0;
        if (save("calibration_after.bin",reply.payload,reply.plen)) return -1;
    }
    valid_count=sample_count=0;
    uint64_t until=monotonic_ns()+10000000000ull;
    while (!stop_requested && monotonic_ns()<until) {
        int rc=read_next_frame(device,&parser,&reply,100);
        if(rc<0) return rc;
        if(rc) notify_sample(&reply);
    }
    keep_model=(selection_test || changed) && valid_count>=30 && !stop_requested;
    printf("{\"kind\":\"%s\",\"calibrated\":%s,\"changed\":%s,\"valid_samples\":%d,\"samples\":%d}\n",
           selection_test?"calibration_ready":"result",keep_model?"true":"false",selection_test?"null":changed?"true":"false",valid_count,sample_count);
    return 0;
}

static int selection_tracking(void) {
    /* Keep this calibrated USB handle. No stored-model upload/reopen. */
    if(samples){fclose(samples);samples=NULL;} /* Finite calibration capture. */
    sample_label="selection";selection_stream=true;
    while(!stop_requested) {
        struct pollfd in={STDIN_FILENO,POLLIN,0};
        if(poll(&in,1,0)>0) {
            char line[128];
            if(!(in.revents&POLLIN) || !fgets(line,sizeof(line),stdin))return 0;
            if(!strcmp(line,"stop\n"))return 0;
            return -1;
        }
        int rc=read_next_frame(device,&parser,&reply,50);
        if(rc<0)return rc;
        if(rc)notify_sample(&reply);
    }
    return 0;
}

static int locate_tracking(void) {
    sample_label="locate";
    /* Sampling begins only after the HDMI owner parks the white-dot frame. */
    uint64_t deadline=monotonic_ns()+12000000000ull;
    bool presented=false;
    while(!stop_requested && monotonic_ns()<deadline && !presented) {
        struct pollfd in={STDIN_FILENO,POLLIN,0};
        if(poll(&in,1,0)>0) {
            char line[128];
            if(!(in.revents&POLLIN) || !fgets(line,sizeof(line),stdin))return -1;
            if(strcmp(line,"locate\n"))return -1;
            presented=true;
        }
        int rc=read_next_frame(device,&parser,&reply,50);
        if(rc<0)return rc;
        if(rc)notify_sample(&reply);
    }
    if(!presented)return -1;
    sample_count=detected_left=detected_right=detected_both=0;
    puts("{\"kind\":\"stage\",\"stage\":\"locate\"}");
    uint64_t until=monotonic_ns()+10000000000ull;
    while(!stop_requested && monotonic_ns()<until) {
        int rc=read_next_frame(device,&parser,&reply,50);
        if(rc<0)return rc;
        if(rc)notify_sample(&reply);
    }
    if(stop_requested)return LIBUSB_ERROR_INTERRUPTED;
    printf("{\"kind\":\"result\",\"diagnostic\":true,\"located\":true,\"samples\":%d,\"left\":%d,\"right\":%d,\"both\":%d}\n",sample_count,detected_left,detected_right,detected_both);
    return 0;
}

static int direction_compare(const void *a,const void *b) {
    double x=*(const double *)a,y=*(const double *)b;
    return (x>y)-(x<y);
}
static double direction_median(double *data,int n) {
    qsort(data,(size_t)n,sizeof(*data),direction_compare);
    return n%2?data[n/2]:(data[n/2-1]+data[n/2])/2;
}
static int direction_session(void) {
    int next=0;selection_stream=true;
    uint64_t deadline=monotonic_ns()+180000000000ull;
    while(!stop_requested && monotonic_ns()<deadline) {
        struct pollfd in={STDIN_FILENO,POLLIN,0};
        if(poll(&in,1,0)>0) {
            char line[128];int point;double x,y;
            if(!(in.revents&POLLIN)||!fgets(line,sizeof(line),stdin))return -1;
            if(sscanf(line,"point %d %lf %lf",&point,&x,&y)==3) {
                if(point!=next || point>=3 || !isfinite(x)||!isfinite(y)||x<0||x>1||y<0||y>1)return -1;
                char label[64];snprintf(label,sizeof(label),"direction_point_%d",point);
                sample_label=label;direction_collect=point;
                uint64_t until=monotonic_ns()+6000000000ull;
                while(!stop_requested && monotonic_ns()<until) {
                    int rc=read_next_frame(device,&parser,&reply,50);
                    if(rc<0){direction_collect=-1;sample_label="direction";return rc;}
                    if(rc)notify_sample(&reply);
                }
                direction_collect=-1;sample_label="direction";
                bool accepted=!stop_requested && direction_n[point]>=60 &&
                    direction_last[point]-direction_first[point]>=2000000000ull;
                fprintf(stderr,"direction_point point=%d samples=%d accepted=%s\n",point,direction_n[point],accepted?"true":"false");
                printf("{\"kind\":\"point\",\"point\":%d,\"accepted\":%s,\"direction\":true}\n",point,accepted?"true":"false");
                if(!accepted)return -1;
                next++;
            } else if(!strcmp(line,"compute\n") && next==3) {
                for(int i=0;i<3;i++) {
                    direction_anchor[i]=direction_median(direction_data[i],direction_n[i]);
                    for(int j=0;j<direction_n[i];j++)direction_data[i][j]=fabs(direction_data[i][j]-direction_anchor[i]);
                    direction_mad[i]=direction_median(direction_data[i],direction_n[i]);
                }
                double sign=direction_anchor[2]>direction_anchor[1]?1:-1;
                double lc=sign*(direction_anchor[0]-direction_anchor[1]);
                double cr=sign*(direction_anchor[2]-direction_anchor[0]);
                if(!direction_fit_valid(direction_anchor,direction_mad)) {
                    fprintf(stderr,"direction_fit_failed lc=%.6f cr=%.6f mad_center=%.6f mad_left=%.6f mad_right=%.6f\n",lc,cr,direction_mad[0],direction_mad[1],direction_mad[2]);return -1;
                }
                direction_trained=true;
                printf("{\"kind\":\"direction_ready\",\"trained\":true,\"center\":%.6f,\"left\":%.6f,\"right\":%.6f,\"samples\":[%d,%d,%d]}\n",direction_anchor[0],direction_anchor[1],direction_anchor[2],direction_n[0],direction_n[1],direction_n[2]);
                return selection_tracking();
            } else if(!strcmp(line,"stop\n"))return 0;
            else return -1;
        }
        int rc=read_next_frame(device,&parser,&reply,50);
        if(rc<0)return rc;
        if(rc)notify_sample(&reply);
    }
    return -1;
}

int main(int argc,char **argv) {
    if((argc!=4 && argc!=5 && argc!=6) || chdir(argv[1])) return 2;
    double width=atof(argv[2]),height=atof(argv[3]);
    direction_mode=argc==5 && !strcmp(argv[4],"--relative-selection");
    selection_test=direction_mode || (argc==5 && (!strcmp(argv[4],"--selection-test") || !strcmp(argv[4],"--selection-test5") || !strcmp(argv[4],"--selection-test9")));
    if(selection_test)calibration_points=!strcmp(argv[4],"--selection-test9")?9:!strcmp(argv[4],"--selection-test5")?5:3;
    bool relaxed=selection_test || (argc==5 && strcmp(argv[4],"--relaxed")==0);
    bool inspect_options=argc==5 && strcmp(argv[4],"--inspect-options")==0;
    bool inspect_points=argc==5 && strcmp(argv[4],"--inspect-points")==0;
    bool check_tracking=argc==5 && strcmp(argv[4],"--check-tracking")==0;
    bool locate=argc==5 && strcmp(argv[4],"--locate")==0;
    bool inspect_model=argc==5 && strcmp(argv[4],"--inspect-model")==0;
    bool restore_model=argc==6 && strcmp(argv[4],"--restore-model")==0;
    bool validate_model=argc==6 && strcmp(argv[4],"--validate-model")==0;
    if(check_tracking)sample_label="tracking_check";
    if(argc==5 && !relaxed && !inspect_options && !inspect_points && !check_tracking && !locate && !inspect_model && strcmp(argv[4],"--check-calibration")) return 2;
    if(argc==6 && !restore_model && !validate_model)return 2;
    if(!isfinite(width)||!isfinite(height)||width<100||width>1000||height<100||height>1000) return 2;
    umask(0077); setvbuf(stdout,NULL,_IOLBF,0);
    signal(SIGINT,handle_signal); signal(SIGTERM,handle_signal);
    libusb_context *ctx=NULL;
    int fd=open("/run/lock/tobii_calibration.lock",O_CREAT|O_RDWR,0600);
    if(fd<0 || flock(fd,LOCK_EX|LOCK_NB)) return 2;
    bool claimed=false; uint32_t terminal_status=0; int err=libusb_init(&ctx);
    if(err) goto cleanup;
    device=libusb_open_device_with_vid_pid(ctx,TOBII_VID,TOBII_PID);
    if(!device) {err=-4;goto cleanup;}
    libusb_set_auto_detach_kernel_driver(device,1);
    err=libusb_claim_interface(device,0); if(err) goto cleanup;
    claimed=true;
    err=libusb_control_transfer(device,0x41,0x41,0,0,NULL,0,1000);
    if(err<0) goto cleanup;
    err=run_tobiifree_handshake(device,&parser,&sequence); if(err) goto cleanup;
    /* Avoid filling the IN image queue during a restored-model upload. */
    if(!restore_model && !validate_model && !inspect_model && !inspect_points) {
        err=send_subscribe(device,sequence++,STREAM_IMAGE_SECONDARY,"calibration_ir_diagnostic");if(err)goto cleanup;
    }
    unsigned char resume[11]={0}; tlv_u32(resume+2,0);
    err=request(0x0c1c,resume,sizeof(resume),2000); if(err) goto cleanup;
    samples=fopen("gaze.csv","w"); if(!samples){err=-1;goto cleanup;}
    write_csv_header(samples);
    session_start=monotonic_ns();
    if(direction_mode){sample_label="direction";puts("{\"kind\":\"ready\"}");err=direction_session();goto cleanup;}
    if(locate){err=locate_tracking();goto cleanup;}
    if(inspect_model){err=read_model("calibration_inspected.bin");if(!err)printf("{\"kind\":\"result\",\"inspected\":true,\"bytes\":%u}\n",reply.plen);goto cleanup;}
    if(restore_model || validate_model) {
        err=ensure_model(argv[5],validate_model);if(err)goto cleanup;
        if(validate_model) {
            err=send_subscribe(device,sequence++,STREAM_IMAGE_SECONDARY,"validation_ir");if(err)goto cleanup;
            err=validate_tracking();
        }
        else puts("{\"kind\":\"result\",\"restored\":true}");
        goto cleanup;
    }
    if(check_tracking){err=tracking_check();goto cleanup;}
    if(inspect_options || inspect_points) {
        /* Read-only protocol audit; no start/clear/compute/model upload. */
        const uint32_t options[]={0x0546,0x07da,0x07ee};
        const uint32_t point_ops[]={0x0460,0x0c62};
        const uint32_t *ops=inspect_points?point_ops:options;
        unsigned count=inspect_points?sizeof(point_ops)/sizeof(point_ops[0]):sizeof(options)/sizeof(options[0]);
        for(unsigned i=0;i<count;i++) {
            int result=request(ops[i],NULL,0,2000);
            fprintf(stderr,"read_only_option op=%04x result=%d status=%08x bytes=%u\n",ops[i],result,failure_status,result?0:reply.plen);
            if(!result) {
                char name[64];snprintf(name,sizeof(name),"option_%04x.bin",ops[i]);
                if(save(name,reply.payload,reply.plen)){err=-1;goto cleanup;}
                fprintf(stderr,"option_payload op=%04x data=",ops[i]);
                for(uint32_t j=0;j<reply.plen && j<256;j++)fprintf(stderr,"%02x",reply.payload[j]);
                fputc('\n',stderr);
            }
        }
        err=0;goto cleanup;
    }
    if(argc==5 && strcmp(argv[4],"--check-calibration")==0) {
        entered=true;
        err=request(0x03f2,NULL,0,2000);
        goto cleanup;
    }
    err=request(0x0596,NULL,0,2000); if(err || reply.plen>sizeof(display_backup))goto cleanup;
    display_backup_len=reply.plen; memcpy(display_backup,reply.payload,reply.plen);
    if(save("display_before.bin",display_backup,display_backup_len)){err=-1;goto cleanup;}
    unsigned char geometry_packet[MAX_PACKET_BYTES];
    size_t geometry_len=build_set_display_area_corners(0,-width/2,height,0,width/2,height,0,-width/2,0,0,geometry_packet);
    display_changed=true;
    err=request(0x05a0,geometry_packet+ENVELOPE_SIZE+TTP_HDR_SIZE,geometry_len-ENVELOPE_SIZE-TTP_HDR_SIZE,2000);
    bool unsupported_geometry=err && reply.magic==TTP_MAGIC_RSP && reply.seq==sequence-1 && reply.op==0x05a0 && reply.status==0x20000501;
    if(err && !unsupported_geometry)goto cleanup;
    err=request(0x0596,NULL,0,2000);if(err)goto cleanup;
    if(unsupported_geometry) {
        if(reply.plen!=display_backup_len || memcmp(reply.payload,display_backup,display_backup_len)){err=-1;goto cleanup;}
        display_changed=false;
        fprintf(stderr,"display_geometry=unchanged_unsupported width_mm=%.1f height_mm=%.1f; accuracy_unverified\n",width,height);
    } else if(reply.plen!=geometry_len-ENVELOPE_SIZE-TTP_HDR_SIZE || memcmp(reply.payload,geometry_packet+ENVELOPE_SIZE+TTP_HDR_SIZE,reply.plen)){err=-1;goto cleanup;}
    if(save("display_configured.bin",reply.payload,reply.plen)){err=-1;goto cleanup;}
    err=begin(); if(err) goto cleanup;
    puts("{\"kind\":\"ready\"}");
    int next_point=0;
    uint64_t session_deadline=monotonic_ns()+(relaxed?420000000000ull:180000000000ull);
    while(!stop_requested && monotonic_ns()<session_deadline) {
        struct pollfd in={STDIN_FILENO,POLLIN,0};
        if(poll(&in,1,0)>0) {
            char line[128]; int point; double x,y;
            if(!(in.revents&POLLIN) || !fgets(line,sizeof(line),stdin)) break;
            if(sscanf(line,"point %d %lf %lf",&point,&x,&y)==3) {
                if(point!=next_point || point>=calibration_points || !isfinite(x) || !isfinite(y) || x<0 || x>1 || y<0 || y>1){err=-1;break;}
                unsigned char payload[37]={0};
                size_t n=2; n+=tlv_q42(payload+n,x); n+=tlv_q42(payload+n,y); n+=tlv_u32(payload+n,3);
                int limit=relaxed?3:1;
                for(int attempt=1;attempt<=limit;attempt++) {
                    int n_before=sample_count,l_before=detected_left,r_before=detected_right,b_before=detected_both;
                    int pl_before=detected_pupil_left,pr_before=detected_pupil_right;
                    char point_label[64];
                    snprintf(point_label,sizeof(point_label),"point_%d_attempt_%d",point,attempt);
                    sample_label=point_label;
                    err=request(0x0406,payload,n,8000);
                    sample_label="calibration";
                    fprintf(stderr,"point_stats point=%d attempt=%d samples=%d left=%d right=%d both=%d pupil_left=%d pupil_right=%d\n",point,attempt,sample_count-n_before,detected_left-l_before,detected_right-r_before,detected_both-b_before,detected_pupil_left-pl_before,detected_pupil_right-pr_before);
                    if(!calibration_retry(attempt,limit,err,failure_status,stop_requested)) break;
                    printf("{\"kind\":\"retry\",\"point\":%d,\"attempt\":%d,\"limit\":%d,\"status\":%u}\n",point,attempt+1,limit,failure_status);
                    uint64_t retry_at=monotonic_ns()+2000000000ull;
                    while(!stop_requested && monotonic_ns()<retry_at) {
                        int rc=read_next_frame(device,&parser,&reply,100);
                        if(rc<0){err=rc;failure_status=0;break;}
                        if(rc)notify_sample(&reply);
                    }
                    if(stop_requested || err!=-1 || failure_status!=0x20000502) break;
                }
                printf("{\"kind\":\"point\",\"point\":%d,\"accepted\":%s,\"status\":%u}\n",point,err?"false":"true",err?failure_status:0);
                if(err) break;
                next_point++;
            } else if(strcmp(line,"compute\n")==0 && next_point==calibration_points) {
                err=compute();
                if(!err && selection_test && keep_model)err=selection_tracking();
                break;
            } else if(strcmp(line,"stop\n")==0) { break;
            } else {err=-1;break;}
        }
        int rc=read_next_frame(device,&parser,&reply,50);
        if(rc<0){err=rc;break;}
        if(rc)notify_sample(&reply);
    }
cleanup:
    terminal_status=failure_status; /* Successful rollback must not erase the cause. */
    stop_requested=0; /* Bounded cleanup commands must still be allowed. */
    if(device && claimed) {
        if(entered && request(0x03fc,NULL,0,2000)) fprintf(stderr,"cleanup_exit_failed\n");
        if(applied && !keep_model && backup_len && !selection_test) {
            int restored=request(0x0456,backup,backup_len,2000);
            if(!restored) restored=request(0x044c,NULL,0,2000);
            if(!restored && (reply.plen!=backup_len || memcmp(reply.payload,backup,backup_len)))restored=-1;
            fprintf(stderr,"rollback_verified=%s\n",restored?"false":"true");
            printf("{\"kind\":\"rollback\",\"verified\":%s}\n",restored?"false":"true");
            if(restored)err=-1;
        }
        if(display_changed && !keep_model && display_backup_len) {
            int restored=request(0x05a0,display_backup,display_backup_len,2000);
            if(!restored)restored=request(0x0596,NULL,0,2000);
            if(!restored && (reply.plen!=display_backup_len || memcmp(reply.payload,display_backup,display_backup_len)))restored=-1;
            fprintf(stderr,"display_rollback_verified=%s\n",restored?"false":"true");
            if(restored)err=-1;
        }
        libusb_control_transfer(device,0x41,0x42,0,0,NULL,0,500);
        libusb_release_interface(device,0);
    }
    if(device)libusb_close(device);
    if(ctx)libusb_exit(ctx);
    if(samples)fclose(samples);
    close(fd);
    if(err)printf("{\"kind\":\"error\",\"code\":%d,\"status\":%u}\n",err,terminal_status?terminal_status:failure_status);
    return err?1:0;
}
