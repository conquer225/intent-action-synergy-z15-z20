#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <libavformat/avformat.h>
#include <libavutil/error.h>

/* This address exists ONLY in the new candidate overlay. --play must not be
 * invoked on eye_wifi.bit or guardianloop_pynq.bit. Inspect/render never map it. */
#define AUDIO_BASE 0x43c20000
#define DISPLAY_BASE 0x43c00000
#define RATE 48000
#define TARGET_QUEUE 6144
#define MAX_FRAMES (600u * RATE)
enum { ID=0, CONTROL=1, QUEUED=2, FLAGS=3, PCM=4, UNDERRUNS=5, CAPACITY=6, SAMPLE_RATE=7 };
static volatile sig_atomic_t stopping;
static uint64_t start_frame;
static void stop_signal(int sig) { (void)sig; stopping=1; }

static int64_t now_ms(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC,&t)) return -1;
    return (int64_t)t.tv_sec*1000+t.tv_nsec/1000000;
}
static void pause_ms(long ms) { struct timespec t={ms/1000,(ms%1000)*1000000}; nanosleep(&t,NULL); }
static void av_error(const char *operation,int code) {
    char text[AV_ERROR_MAX_STRING_SIZE]; av_strerror(code,text,sizeof text);
    fprintf(stderr,"%s: %s\n",operation,text);
}
struct reader { AVFormatContext *format; AVPacket *packet; int offset,stream,eof; uint64_t frames; };
static int open_pcm(struct reader *r,const char *path) {
    struct stat st;
    if (stat(path,&st) || !S_ISREG(st.st_mode) || st.st_size<=0 || st.st_size>512*1024*1024) {
        fprintf(stderr,"Expected a local regular WAV file, at most 512 MiB\n"); return -1;
    }
    AVDictionary *options=NULL;
    av_dict_set(&options,"protocol_whitelist","file",0);
    int rc=avformat_open_input(&r->format,path,av_find_input_format("wav"),&options);
    av_dict_free(&options);
    if (rc<0) { av_error("Open WAV",rc); return -1; }
    if (r->format->nb_streams!=1) { fprintf(stderr,"Expected one PCM stream\n"); return -1; }
    AVCodecParameters *p=r->format->streams[0]->codecpar;
    if (p->codec_id!=AV_CODEC_ID_PCM_S16LE || p->sample_rate!=RATE || p->channels!=2 || p->bits_per_coded_sample!=16) {
        fprintf(stderr,"Prepare the asset as 48 kHz PCM16 stereo before playback\n"); return -1;
    }
    r->packet=av_packet_alloc();
    return r->packet ? 0 : -1;
}
static void close_pcm(struct reader *r) { av_packet_free(&r->packet); avformat_close_input(&r->format); }
static int scaled_sample(const uint8_t *p,int volume) {
    int value=p[0]+((int)p[1]<<8);
    if (value>=32768) value-=65536;
    return value*volume/100;
}
static int read_pcm(struct reader *r,uint32_t *words,int limit,int volume) {
    int count=0;
    while (count<limit) {
        if (r->offset>=r->packet->size) {
            if (r->eof) break;
            av_packet_unref(r->packet);
            int rc=av_read_frame(r->format,r->packet);
            if (rc==AVERROR_EOF) { r->eof=1; break; }
            if (rc<0) { av_error("Read PCM",rc); return -1; }
            if (r->packet->stream_index!=r->stream || r->packet->size%4) {
                fprintf(stderr,"Malformed PCM packet\n"); return -1;
            }
            r->offset=0;
            if (!r->packet->size) continue;
        }
        if (r->frames>=MAX_FRAMES) { fprintf(stderr,"Audio exceeds ten minutes\n"); return -1; }
        const uint8_t *p=r->packet->data+r->offset;
        uint16_t left=(uint16_t)scaled_sample(p,volume),right=(uint16_t)scaled_sample(p+2,volume);
        words[count++]=(uint32_t)left|((uint32_t)right<<16);
        r->offset+=4; r->frames++;
    }
    return count;
}
static void report(const char *phase,uint64_t submitted,uint32_t queued,uint32_t underruns) {
    char text[320];
    uint64_t presented=submitted>=queued ? submitted-queued : 0;
    int n=snprintf(text,sizeof text,"{\"phase\":\"%s\",\"rate\":48000,\"submitted_frames\":%" PRIu64 ",\"queued_frames\":%u,\"position_frames_estimate\":%" PRIu64 ",\"underruns\":%u,\"audible_verified\":false}\n",phase,submitted,queued,start_frame+presented,underruns);
    if (n>0 && n<(int)sizeof text && write(STDOUT_FILENO,text,(size_t)n)<0 && errno!=EAGAIN && errno!=EINTR) stopping=1;
}
static void set_control(volatile uint32_t *ip,uint32_t value) { ip[CONTROL]=value; __sync_synchronize(); }
static int play_pcm(struct reader *r,int volume) {
    signal(SIGINT,stop_signal); signal(SIGTERM,stop_signal); signal(SIGPIPE,SIG_IGN);
    int rc=-1,mem=-1,lock=-1,output_flags=-1;
    volatile uint32_t *ip=MAP_FAILED,*display=MAP_FAILED;
    uint32_t words[512],queued=0,underruns=0;
    uint64_t submitted=0,last_presented=0;
    int64_t last_progress=now_ms(),last_report=0;
    lock=open("/run/lock/guardianloop_hdmi_audio.lock",O_WRONLY|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0600);
    if (lock<0 || flock(lock,LOCK_EX|LOCK_NB)) { fprintf(stderr,"Another HDMI audio player owns the device\n"); goto done; }
    mem=open("/dev/mem",O_RDWR|O_SYNC|O_CLOEXEC);
    if (mem<0) { perror("Open /dev/mem"); goto done; }
    ip=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,mem,AUDIO_BASE);
    if (ip==MAP_FAILED) { perror("Map candidate PCM registers"); goto done; }
    if (ip[ID]!=0x474c4101 || ip[SAMPLE_RATE]!=RATE || ip[CAPACITY]!=8191) {
        fprintf(stderr,"Candidate PCM identity/configuration does not match; no control writes\n");
        munmap((void *)ip,4096); ip=MAP_FAILED; goto done;
    }
    set_control(ip,2); pause_ms(1); set_control(ip,0);
    int64_t deadline=now_ms()+1000;
    while (ip[FLAGS]&4) {
        if (stopping || now_ms()>deadline) { fprintf(stderr,"PCM reset/clock did not become ready\n"); goto done; }
        pause_ms(1);
    }
    display=mmap(NULL,4096,PROT_READ,MAP_SHARED,mem,DISPLAY_BASE);
    if (display==MAP_FAILED || display[0]!=0x4f534438) { fprintf(stderr,"Display status is not ready\n"); goto done; }
    uint32_t scan=display[3]; int scans=0;
    deadline=now_ms()+1000;
    while (scans<2) {
        uint32_t next=display[3];
        if (next!=scan) { scans++; scan=next; }
        if (stopping || now_ms()>deadline) { fprintf(stderr,"Display scan is not running\n"); goto done; }
        pause_ms(2);
    }
    while (submitted<TARGET_QUEUE && !stopping) {
        int n=read_pcm(r,words,(int)(TARGET_QUEUE-submitted)>512 ? 512 : (int)(TARGET_QUEUE-submitted),volume);
        if (n<0) goto done;
        if (!n) break;
        for (int i=0;i<n;i++) ip[PCM]=words[i];
        __sync_synchronize(); submitted+=(unsigned)n;
    }
    if (!submitted || stopping) { fprintf(stderr,"No PCM samples prepared for playback\n"); goto done; }
    output_flags=fcntl(STDOUT_FILENO,F_GETFL);
    if (output_flags<0 || fcntl(STDOUT_FILENO,F_SETFL,output_flags|O_NONBLOCK)<0) { perror("Set nonblocking status output"); goto done; }
    set_control(ip,1);
    last_progress=now_ms();
    while (!stopping) {
        queued=ip[QUEUED]; underruns=ip[UNDERRUNS];
        if (queued>8191 || queued>submitted) { fprintf(stderr,"Invalid PCM FIFO count\n"); goto done; }
        uint64_t presented=submitted-queued;
        if (presented!=last_presented) { last_presented=presented; last_progress=now_ms(); }
        if (r->eof && !queued) { rc=0; break; }
        if (now_ms()-last_progress>2000) { fprintf(stderr,"PCM consumption stopped\n"); goto done; }
        if (queued<TARGET_QUEUE && !r->eof) {
            int n=read_pcm(r,words,TARGET_QUEUE-queued>512 ? 512 : (int)(TARGET_QUEUE-queued),volume);
            if (n<0) goto done;
            for (int i=0;i<n;i++) ip[PCM]=words[i];
            __sync_synchronize(); submitted+=(unsigned)n;
        } else pause_ms(2);
        if (now_ms()-last_report>=100) { report("feeding",submitted,ip[QUEUED],ip[UNDERRUNS]); last_report=now_ms(); }
    }
    if (stopping) rc=0;
done:
    if (ip!=MAP_FAILED) {
        queued=ip[QUEUED]; underruns=ip[UNDERRUNS];
        set_control(ip,2);
        if (output_flags>=0) report(rc ? "error" : stopping ? "stopped" : "completed",submitted,queued,underruns);
        munmap((void *)ip,4096);
    }
    if (display!=MAP_FAILED) munmap((void *)display,4096);
    if (mem>=0) close(mem);
    if (lock>=0) close(lock);
    if (output_flags>=0) fcntl(STDOUT_FILENO,F_SETFL,output_flags);
    return rc;
}
int main(int argc,char **argv) {
    if (argc<3 || (strcmp(argv[1],"--inspect") && strcmp(argv[1],"--render") && strcmp(argv[1],"--play"))) {
        fprintf(stderr,"Usage: pcm_player --inspect WAV | --render WAV NEW.raw | --play WAV [--volume 0..100] [--start-frame N]\n"); return 2;
    }
    int render=!strcmp(argv[1],"--render"),play=!strcmp(argv[1],"--play"),volume=10,index=render ? 4 : 3;
    if (argc<index) return 2;
    int seen_volume=0,seen_start=0;
    for (;index<argc;index+=2) {
        if (index+1>=argc) return 2;
        char *end; errno=0; long value=strtol(argv[index+1],&end,10);
        if (errno || end==argv[index+1] || *end || value<0) return 2;
        if (!strcmp(argv[index],"--volume") && !seen_volume && value<=100) {
            volume=(int)value;seen_volume=1;
        } else if (!strcmp(argv[index],"--start-frame") && !seen_start && (uint64_t)value<MAX_FRAMES) {
            start_frame=(uint64_t)value;seen_start=1;
        } else return 2;
    }
    av_log_set_level(AV_LOG_ERROR);
    struct reader r={0};
    if (open_pcm(&r,argv[2])) { close_pcm(&r); return 1; }
    uint32_t words[512];
    while(r.frames<start_frame) {
        uint64_t remaining=start_frame-r.frames;
        int skipped=read_pcm(&r,words,remaining>512 ? 512 : (int)remaining,0);
        if (skipped<=0) { fprintf(stderr,"Start position is past available audio\n"); close_pcm(&r); return 1; }
    }
    if (play) { int rc=play_pcm(&r,volume); close_pcm(&r); return rc ? 1 : 0; }
    FILE *out=NULL;
    if (render) { out=fopen(argv[3],"wbx"); if (!out) { perror("Create exclusive PCM output"); close_pcm(&r); return 1; } }
    int rc=0,n;
    while ((n=read_pcm(&r,words,512,volume))>0) {
        if (out && fwrite(words,sizeof words[0],(size_t)n,out)!=(size_t)n) { rc=1; break; }
    }
    if (n<0 || r.frames==start_frame) rc=1;
    if (out && fclose(out)) rc=1;
    if (render && rc) unlink(argv[3]);
    if (!rc) printf("{\"phase\":\"%s\",\"frames\":%" PRIu64 ",\"start_frame\":%" PRIu64 ",\"rate\":48000,\"channels\":2,\"volume_percent\":%d,\"hardware_opened\":false}\n",render ? "rendered" : "inspected",r.frames-start_frame,start_frame,volume);
    close_pcm(&r); return rc;
}
