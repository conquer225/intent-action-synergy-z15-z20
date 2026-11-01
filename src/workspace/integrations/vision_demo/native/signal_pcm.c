#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef _WIN32
#include <sys/file.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#endif

/* Adapted from retained GuardianLoop PCM player; original source remains unchanged. */
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
#ifndef _WIN32
static void stop_signal(int sig) { (void)sig; stopping=1; }
#endif
static uint64_t fade_stop_at=UINT64_MAX;


static uint16_t u16(const uint8_t *b){return (uint16_t)(b[0]|((uint16_t)b[1]<<8));}
static uint32_t u32(const uint8_t *b){return (uint32_t)b[0]|((uint32_t)b[1]<<8)|((uint32_t)b[2]<<16)|((uint32_t)b[3]<<24);}
struct reader {FILE *file;uint64_t frames,total;long offset;int eof;};
static int open_pcm(struct reader *r,const char *path){
 uint8_t h[40];r->file=fopen(path,"rb");if(!r->file)return -1;
 if(fread(h,1,12,r->file)!=12||memcmp(h,"RIFF",4)||memcmp(h+8,"WAVE",4))return -1;
 int format=0;long end; if(fseek(r->file,0,SEEK_END))return -1;end=ftell(r->file);if(end<44||end>512*1024*1024)return -1;
 if(fseek(r->file,12,SEEK_SET))return -1;
 while(ftell(r->file)<=end-8){
  if(fread(h,1,8,r->file)!=8)return -1;
  uint32_t n=u32(h+4);long at=ftell(r->file);
  if(n>(uint32_t)(end-at))return -1;
  if(!memcmp(h,"fmt ",4)){
   if(n<16||fread(h,1,16,r->file)!=16)return -1;
   if(u16(h)!=1||u16(h+2)!=2||u32(h+4)!=RATE||u16(h+12)!=4||u16(h+14)!=16)return -1;
   format=1;
  }else if(!memcmp(h,"data",4)){
   if(!format||n%4||!n||n/4>MAX_FRAMES)return -1;
   r->offset=at;r->total=n/4;return 0;
  }
  if(n>0x7ffffffe||fseek(r->file,at+(long)n+(n&1),SEEK_SET))return -1;
 }
 return -1;
}
static void close_pcm(struct reader *r){if(r->file)fclose(r->file);r->file=NULL;}
static int read_pcm(struct reader *r,uint32_t *words,int limit,int volume){
 int count=0;
 if(stopping&&fade_stop_at==UINT64_MAX)fade_stop_at=r->frames;
 while(count<limit&&r->frames<r->total){
  if(fade_stop_at!=UINT64_MAX&&r->frames-fade_stop_at>=RATE){r->eof=1;break;}
  uint8_t b[4];if(fread(b,1,4,r->file)!=4)return -1;
  double gain=1.;uint64_t relative=r->frames>=start_frame?r->frames-start_frame:0;
  if(relative<RATE)gain=(double)relative/RATE;
  uint64_t remaining=r->total-r->frames;if(remaining<RATE&&gain>(double)remaining/RATE)gain=(double)remaining/RATE;
  if(fade_stop_at!=UINT64_MAX){double stop_gain=1.-(double)(r->frames-fade_stop_at)/RATE;if(gain>stop_gain)gain=stop_gain;}
  int left=(int16_t)u16(b),right=(int16_t)u16(b+2);
  int16_t l=(int16_t)(left*volume/100.*gain),rr=(int16_t)(right*volume/100.*gain);
  words[count++]=(uint16_t)l|((uint32_t)(uint16_t)rr<<16);r->frames++;
 }
 if(r->frames>=r->total)r->eof=1;
 return count;
}

#ifndef _WIN32
static int64_t now_ms(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC,&t)) return -1;
    return (int64_t)t.tv_sec*1000+t.tv_nsec/1000000;
}
static void pause_ms(long ms) { struct timespec t={ms/1000,(ms%1000)*1000000}; nanosleep(&t,NULL); }
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
    while (1) {
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

#endif

int main(int argc,char **argv){
 if(argc<3)return 2;
 int render=!strcmp(argv[1],"--render"),play=!strcmp(argv[1],"--play"),inspect=!strcmp(argv[1],"--inspect");
 if(!render&&!play&&!inspect)return 2;
 int volume=10,index=render?4:3;if(argc<index)return 2;
 for(;index<argc;index+=2){
  if(index+1>=argc)return 2;
  char *end;errno=0;long value=strtol(argv[index+1],&end,10);
  if(errno||end==argv[index+1]||*end||value<0)return 2;
  if(!strcmp(argv[index],"--volume")&&value<=100)volume=(int)value;
  else if(!strcmp(argv[index],"--start-frame")&&(uint64_t)value<MAX_FRAMES)start_frame=(uint64_t)value;
  else return 2;
 }
 struct reader r={0};if(open_pcm(&r,argv[2])){fprintf(stderr,"Expected regular PCM16 stereo48kHz WAV\n");close_pcm(&r);return 1;}
 if(start_frame>=r.total||fseek(r.file,r.offset+(long)(start_frame*4),SEEK_SET)){close_pcm(&r);return 1;}r.frames=start_frame;
 if(play){
#ifdef _WIN32
  fprintf(stderr,"Hardware playback unavailable on Windows\n");close_pcm(&r);return 2;
#else
  int rc=play_pcm(&r,volume);close_pcm(&r);return rc?1:0;
#endif
 }
 FILE *out=NULL;if(render){out=fopen(argv[3],"wbx");if(!out){close_pcm(&r);return 1;}}
 uint32_t words[512];int n,rc=0;while((n=read_pcm(&r,words,512,volume))>0)if(out&&fwrite(words,4,n,out)!=(size_t)n){rc=1;break;}
 if(n<0)rc=1;
 if(out&&fclose(out))rc=1;
 if(!rc)printf("{\"hardware_opened\":false,\"frames\":%" PRIu64 ",\"fade_frames\":48000}\n",r.frames-start_frame);
 close_pcm(&r);return rc;
}
