#define _GNU_SOURCE
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

enum { MAX_ROWS=3000, WIDTH=1280, HEIGHT=720, STRIDE=3840 };
enum { OK=0, CONFIG=1, SCHEDULER=2, OWNER=3, DMA=4, PARK=5, SKIP=6,
       COPY_LATE=7, ACK_LATE=8, FLUSH=9, STOPPED=10, CAPACITY=11, CPU_BUDGET=12,
       HEARTBEAT=13 };
typedef uint32_t (*read_fn)(void);
typedef int (*park_fn)(unsigned);
typedef int (*sync_fn)(void *, unsigned, int, size_t, size_t);
typedef uint64_t (*clock_fn)(int);
typedef uint32_t (*read32_fn)(uint32_t);
typedef void (*write32_fn)(uint32_t,uint32_t);

static read32_fn vdma_read;
static write32_fn vdma_write;

int gl_scan_bind_vdma(read32_fn read32,write32_fn write32)
{
    if(!read32 || !write32) return 0;
    vdma_read=read32;vdma_write=write32;
    return 1;
}

int gl_scan_request_park(unsigned index)
{
    /* Existing eye_wifi MM2S mapping and XAxiVdma_StartParking, without its
       display_park wrapper's 500ms sleep/poll loop. No new register map. */
    const uint32_t base=0x43000000U;
    if(index>2 || !vdma_read || !vdma_write) return 0;
    uint32_t control=vdma_read(base);
    if(!(control&1U) || (vdma_read(base+4)&0x80000ff1U)) return 0;
    uint32_t park=vdma_read(base+0x28);
    vdma_write(base+0x28,(park&~31U)|index);
    vdma_write(base,control&~2U);
    return 1;
}

struct corner { uint32_t x, y, width, height; const uint8_t *off, *on, *chosen_off, *chosen_on; };
struct frame { uint8_t *data; uint32_t bo, coherent; size_t offset; };
struct feedback { uint32_t x,y,width,height; const uint8_t *states; uint32_t count; };
struct config {
    read_fn counter, index, status;
    park_fn park;
    sync_fn sync;
    clock_fn software_clock;
    void *device;
    struct frame frames[3];
    struct corner corners[4];
    const uint8_t *masks;
    uint32_t mask_count, initial_mask;
    uint64_t duration_ns, period_ns;
    int realtime, cpu;
    const uint8_t *base;
    uint32_t initialized_mask, require_heartbeat, heartbeat_ms;
    struct feedback feedback;
};
struct receipt {
    uint32_t before, after, target, requested, active, mask, status, reserved;
    uint64_t ack_ns, park_ns, copy_ns, flush_ns, copied_bytes, flushed_bytes;
};
struct outcome {
    uint32_t error, count, origin, initial_index, end_counter, end_index;
    uint32_t policy, priority, cpu, scheduler_errno;
    uint64_t onset_ns, end_ns, last_copy_ns, last_flush_ns, worker_cpu_ns, max_cycle_cpu_ns;
};
#ifdef GL_SCAN_DIAGNOSTIC
struct trace { uint64_t monotonic[9], raw[9], cpu[9]; };
#endif
struct session {
    struct config config;
    pthread_t thread;
    atomic_int cancel, done, origin_ready, selected;
    atomic_uint feedback;
    atomic_uint published, heartbeat_ms;
    struct outcome result;
    struct receipt rows[MAX_ROWS];
    uint8_t masks[3];
    uint32_t prepared[3];
    int choices[3];
    uint32_t feedback_states[3];
    uint32_t initialized_mask;
#ifdef GL_SCAN_DIAGNOSTIC
    struct trace traces[MAX_ROWS];
#endif
};

size_t gl_scan_config_size(void) { return sizeof(struct config); }
size_t gl_scan_receipt_size(void) { return sizeof(struct receipt); }
size_t gl_scan_outcome_size(void) { return sizeof(struct outcome); }
static __thread clock_fn test_clock;

static uint64_t clock_ns(clockid_t id)
{
    if(test_clock) return test_clock(id);
    struct timespec now;
    clock_gettime(id, &now);
    return (uint64_t)now.tv_sec*1000000000ULL + now.tv_nsec;
}
static uint64_t now_ns(void) { return clock_ns(CLOCK_MONOTONIC); }
#ifdef GL_SCAN_DIAGNOSTIC
static void trace_phase(struct session *s,unsigned phase)
{
    if(s->config.software_clock || s->result.count>=MAX_ROWS) return;
    struct trace *t=&s->traces[s->result.count];
    t->monotonic[phase]=clock_ns(CLOCK_MONOTONIC);
    t->raw[phase]=clock_ns(CLOCK_MONOTONIC_RAW);
    t->cpu[phase]=clock_ns(CLOCK_THREAD_CPUTIME_ID);
}
int gl_scan_trace(void *session,struct trace *rows,uint32_t capacity)
{
    struct session *s=session;
    if(!rows || capacity<MAX_ROWS || !atomic_load_explicit(&s->done,memory_order_acquire)) return -1;
    uint32_t count=s->result.count+(s->result.error && s->result.count<MAX_ROWS);
    memcpy(rows,s->traces,count*sizeof(*rows));
    return (int)count;
}
#define TRACE(s,p) trace_phase(s,p)
#else
#define TRACE(s,p) ((void)0)
#endif
static int fault(struct session *s)
{
    if (s->config.status() & 0x80000ff1U) return DMA;
    if (atomic_load(&s->cancel)) return STOPPED;
    if (s->config.require_heartbeat &&
        (uint32_t)((uint32_t)(now_ns()/1000000ULL)-atomic_load(&s->heartbeat_ms))>350U)
        return HEARTBEAT;
    return OK;
}
static int valid(const struct config *c)
{
    if (!c || !c->counter || !c->index || !c->status || !c->park || !c->sync ||
        !c->masks || c->mask_count < 4 || c->mask_count > MAX_ROWS ||
        c->initial_mask > 15 || !c->duration_ns || c->duration_ns>45000000000ULL ||
        c->period_ns!=16500000ULL || (c->realtime!=0 && c->realtime!=1) ||
        (c->software_clock && c->realtime) || c->masks[0]!=c->initial_mask ||
        c->initialized_mask>7 || c->initialized_mask==0 ||
        (c->initialized_mask!=7 && !c->base) || c->require_heartbeat>1) return 0;
    for (unsigned i=0;i<c->mask_count;i++) if(c->masks[i]>15) return 0;
    for (unsigned i=0;i<3;i++)
        if(!c->frames[i].data || c->frames[i].coherent>1) return 0;
    for (unsigned i=0;i<4;i++) {
        const struct corner *p=&c->corners[i];
        if(!p->off || !p->on || !p->chosen_off || !p->chosen_on || !p->width || !p->height ||
           p->width>WIDTH || p->height>HEIGHT || p->x>WIDTH-p->width ||
           p->y>HEIGHT-p->height) return 0;
    }
    const struct feedback *f=&c->feedback;
    if(f->count && (!f->states || f->count>32 || !f->width || !f->height ||
        f->width>WIDTH || f->height>HEIGHT || f->x>WIDTH-f->width || f->y>HEIGHT-f->height)) return 0;
    return 1;
}

int gl_scan_validate(const struct config *config) { return valid(config); }

/* Port of the existing dirty-corner/full-width-band preparation, no MMIO map. */
static int prepare(struct session *s,unsigned index,uint32_t target,uint32_t latest,
                   struct receipt *row)
{
    struct config *c=&s->config;
    if(c->index()==index) return OWNER;
    uint32_t ordinal=target-s->result.origin;
    if(ordinal>=c->mask_count) return CAPACITY;
    uint8_t mask=c->masks[ordinal], old=s->masks[index];
    int selected=atomic_load(&s->selected),old_selected=s->choices[index];
    int full=!(s->initialized_mask&(1U<<index));
    uint32_t band_y[5],band_h[5],bands=0;
    uint64_t started=now_ns();
    if(full) {
        memcpy(c->frames[index].data,c->base,HEIGHT*STRIDE);
        row->copied_bytes+=HEIGHT*STRIDE;
    }
    for(unsigned i=0;i<4;i++) if(full || ((old^mask)&(1U<<i)) ||
                                 ((selected==(int)i)!=(old_selected==(int)i))) {
        const struct corner *p=&c->corners[i];
        const uint8_t *source=selected==(int)i ?
            ((mask&(1U<<i))?p->chosen_on:p->chosen_off) : ((mask&(1U<<i))?p->on:p->off);
        for(unsigned y=0;y<p->height;y++)
            memcpy(c->frames[index].data+(p->y+y)*STRIDE+p->x*3,
                   source+y*p->width*3,p->width*3);
        row->copied_bytes+=(uint64_t)p->height*p->width*3;
        unsigned b;
        for(b=0;b<bands;b++) if(band_y[b]==p->y && band_h[b]==p->height) break;
        if(b==bands) { band_y[bands]=p->y;band_h[bands++]=p->height; }
    }
    unsigned feedback=atomic_load(&s->feedback);
    const struct feedback *f=&c->feedback;
    if(f->count && (full || s->feedback_states[index]!=feedback)) {
        const uint8_t *source=f->states+(size_t)feedback*f->width*f->height*3;
        for(unsigned y=0;y<f->height;y++)
            memcpy(c->frames[index].data+(f->y+y)*STRIDE+f->x*3,
                   source+y*f->width*3,f->width*3);
        row->copied_bytes+=(uint64_t)f->width*f->height*3;
        band_y[bands]=f->y;band_h[bands++]=f->height;
    }
    row->copy_ns=now_ns()-started;
    started=now_ns();
    if(full) { bands=1;band_y[0]=0;band_h[0]=HEIGHT; }
    for(unsigned b=0;b<bands;b++) {
        size_t size=(size_t)band_h[b]*STRIDE;
        if(!c->frames[index].coherent &&
           c->sync(c->device,c->frames[index].bo,0,size,
                   c->frames[index].offset+(size_t)band_y[b]*STRIDE)) return FLUSH;
        if(!c->frames[index].coherent) row->flushed_bytes+=size;
    }
    row->flush_ns=now_ns()-started;
    s->result.last_copy_ns=row->copy_ns;
    s->result.last_flush_ns=row->flush_ns;
    if(c->counter()!=latest) return COPY_LATE;
    s->masks[index]=mask;
    s->choices[index]=selected;
    s->feedback_states[index]=feedback;
    s->initialized_mask|=1U<<index;
    s->prepared[index]=target;
    return fault(s);
}

static int park(struct session *s,unsigned target,uint32_t before,uint32_t expected,
                struct receipt *row,int initial)
{
    struct config *c=&s->config;
    uint64_t started=now_ns();
    if(!initial) TRACE(s,1);
    if(!c->park(target)) return PARK;
    if(!initial) TRACE(s,2);
    uint32_t after=c->counter();
    while(after==before || c->index()!=target) {
        if(c->software_clock && after!=before) return PARK;
        if(now_ns()-started>(initial?50000000ULL:c->period_ns*3/2)) return PARK;
        int error=fault(s);
        if(error) return error;
        uint64_t expected_ns=s->result.onset_ns+
            (uint32_t)(expected-s->result.origin)*c->period_ns;
        /* One absolute wake avoids dozens of short timer sleeps per frame.
           Leave 4ms for edge polling within the unchanged 8ms cycle budget. */
        if(initial) {
            struct timespec delay={0,200000};
            nanosleep(&delay,NULL);
        } else if(now_ns()+4000000ULL<expected_ns) {
            uint64_t wake_ns=expected_ns-4000000ULL;
            struct timespec wake={(time_t)(wake_ns/1000000000ULL),
                                  (long)(wake_ns%1000000000ULL)};
            int sleep_error=clock_nanosleep(CLOCK_MONOTONIC,TIMER_ABSTIME,&wake,NULL);
            if(sleep_error && sleep_error!=EINTR) return PARK;
        }
        after=c->counter();
    }
    if(!initial) TRACE(s,3);
    row->park_ns=now_ns()-started;
    row->before=before;row->after=after;row->target=expected;
    row->requested=target;row->active=c->index();
    if(!initial) TRACE(s,4);
    row->status=c->status();
    if(!initial) TRACE(s,5);
    row->ack_ns=now_ns();
    if(!initial) TRACE(s,6);
    if(!initial && after!=expected) return SKIP;
    return fault(s);
}

static int execute(struct session *s)
{
    struct config *c=&s->config;
    struct outcome *result=&s->result;
    unsigned current=c->index(),active=(current+1)%3;
    if(current>2 || !(s->initialized_mask&(1U<<active))) return OWNER;
    struct receipt first={0};
    /* The initial target is prepared while inactive; the old menu is copied only after release. */
    uint32_t before=c->counter();
    int error=park(s,active,before,before+1,&first,1);
    if(error) return error;
    result->origin=first.after;result->initial_index=active;result->onset_ns=first.ack_ns;
    uint32_t latest=result->origin;
    for(unsigned ahead=1;ahead<=2;ahead++) {
        struct receipt prep={0};
        error=prepare(s,(active+ahead)%3,latest+ahead,latest,&prep);
        if(error) return error;
    }
    atomic_store_explicit(&s->origin_ready,1,memory_order_release);
    uint64_t previous=result->onset_ns;
    while(now_ns()-result->onset_ns<c->duration_ns) {
        TRACE(s,0);
        if(result->count>=MAX_ROWS || latest-result->origin+3>=c->mask_count) return CAPACITY;
        if((error=fault(s))) return error;
        if(c->counter()!=latest) return SKIP;
        if(c->index()!=active) return OWNER;
        unsigned target=(active+1)%3;
        if(s->prepared[target]!=latest+1) return CONFIG;
        struct receipt *row=&s->rows[result->count];
        uint64_t cpu_start=clock_ns(CLOCK_THREAD_CPUTIME_ID);
        error=park(s,target,latest,latest+1,row,0);
        TRACE(s,7);
        row->mask=c->masks[(latest+1)-result->origin];
        row->reserved=(uint32_t)(s->choices[target]+1);
        if(error) return error;
        if(row->ack_ns<=previous || row->ack_ns-previous>c->period_ns*3/2) return ACK_LATE;
        previous=row->ack_ns;
        latest=row->after;
        unsigned released=active;active=target;
        error=prepare(s,released,latest+2,latest,row);
        TRACE(s,8);
        if(error) return error;
        uint64_t cycle_cpu=clock_ns(CLOCK_THREAD_CPUTIME_ID)-cpu_start;
        if(cycle_cpu>result->max_cycle_cpu_ns) result->max_cycle_cpu_ns=cycle_cpu;
        if(cycle_cpu>8000000ULL) return CPU_BUDGET;
        result->count++;
        atomic_store_explicit(&s->published,result->count,memory_order_release);
    }
    return OK;
}

static void *worker(void *opaque)
{
    struct session *s=opaque;
    test_clock=s->config.software_clock;
    uint64_t cpu_start=clock_ns(CLOCK_THREAD_CPUTIME_ID);
    if(s->config.realtime) {
        cpu_set_t allowed,chosen;
        int cpu=s->config.cpu;
        if(cpu<0 || cpu>=CPU_SETSIZE || pthread_getaffinity_np(pthread_self(),sizeof(allowed),&allowed) ||
           !CPU_ISSET(cpu,&allowed)) { s->result.error=SCHEDULER;goto done; }
        CPU_ZERO(&chosen);CPU_SET(cpu,&chosen);
        struct sched_param param={.sched_priority=1};
        int error=pthread_setaffinity_np(pthread_self(),sizeof(chosen),&chosen);
        if(!error) error=pthread_setschedparam(pthread_self(),SCHED_RR,&param);
        if(error) {s->result.scheduler_errno=error;s->result.error=SCHEDULER;goto done;}
    }
    struct sched_param actual;
    int policy;
    pthread_getschedparam(pthread_self(),&policy,&actual);
    s->result.policy=policy;s->result.priority=actual.sched_priority;s->result.cpu=sched_getcpu();
    s->result.error=execute(s);
done:
    s->result.end_counter=s->config.counter();s->result.end_index=s->config.index();
    s->result.end_ns=now_ns();
    s->result.worker_cpu_ns=clock_ns(CLOCK_THREAD_CPUTIME_ID)-cpu_start;
    struct sched_param ordinary={.sched_priority=0};
    pthread_setschedparam(pthread_self(),SCHED_OTHER,&ordinary);
    atomic_store_explicit(&s->done,1,memory_order_release);
    return NULL;
}

void *gl_scan_start(const struct config *config)
{
    if(!valid(config)) {errno=EINVAL;return NULL;}
    struct session *s=malloc(sizeof(*s));
    if(!s) return NULL;
    memset(s,0,sizeof(*s));
    /* Touch every record page before the real-time thread is created. */
    volatile unsigned char *pages=(volatile unsigned char *)s;
    for(size_t i=0;i<sizeof(*s);i+=4096) pages[i]=0;
    s->config=*config;
    for(unsigned i=0;i<3;i++) {s->masks[i]=config->initial_mask;s->choices[i]=-1;s->feedback_states[i]=UINT32_MAX;}
    s->initialized_mask=config->initialized_mask;
    atomic_init(&s->cancel,0);atomic_init(&s->done,0);
    atomic_init(&s->origin_ready,0);atomic_init(&s->published,0);
    atomic_init(&s->selected,-1);atomic_init(&s->heartbeat_ms,config->heartbeat_ms);
    atomic_init(&s->feedback,0);
    int error=pthread_create(&s->thread,NULL,worker,s);
    if(error) {free(s);errno=error;return NULL;}
    return s;
}
int gl_scan_done(void *session)
{
    return atomic_load_explicit(&((struct session *)session)->done,memory_order_acquire);
}
void gl_scan_cancel(void *session) {atomic_store(&((struct session *)session)->cancel,1);}
void gl_scan_touch(void *session,uint32_t stamp_ms)
{ atomic_store(&((struct session *)session)->heartbeat_ms,stamp_ms); }
int gl_scan_select(void *session,int selected)
{
    if(selected < -1 || selected > 3) return 0;
    atomic_store(&((struct session *)session)->selected,selected);
    return 1;
}
int gl_scan_feedback(void *session,uint32_t index)
{
    struct session *s=session;
    if(index>=s->config.feedback.count) return 0;
    atomic_store(&s->feedback,index);
    return 1;
}
int gl_scan_read(void *session,uint32_t cursor,struct outcome *out,
                 struct receipt *rows,uint32_t capacity)
{
    struct session *s=session;
    if(!out || !rows || capacity<1 || capacity>8) return -1;
    uint32_t count=atomic_load_explicit(&s->published,memory_order_acquire);
    if(cursor>count) return -1;
    memset(out,0,sizeof(*out));
    if(gl_scan_done(s)) *out=s->result;
    else if(atomic_load_explicit(&s->origin_ready,memory_order_acquire)) {
        out->origin=s->result.origin;out->initial_index=s->result.initial_index;
        out->onset_ns=s->result.onset_ns;
    }
    uint32_t available=count-cursor;
    if(available>capacity) available=capacity;
    /* Published records are immutable until collect, serialized by the Python adapter. */
    memcpy(rows,s->rows+cursor,available*sizeof(*rows));
    out->count=count;
    return (int)available;
}
int gl_scan_collect(void *session,struct outcome *out,struct receipt *rows,uint32_t capacity)
{
    struct session *s=session;
    if(!gl_scan_done(s) || capacity<MAX_ROWS) return 0;
    if(pthread_join(s->thread,NULL)) return 0;
    *out=s->result;
    /* Include the failed in-flight record, when any, without calling it accepted. */
    memcpy(rows,s->rows,sizeof(s->rows));
    free(s);
    return 1;
}
