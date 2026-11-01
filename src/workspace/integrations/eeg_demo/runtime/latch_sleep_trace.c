#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdint.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>

/* Process-local diagnostic: observe the original sleep, never shorten it. */
struct sleep_trace {
    uint64_t calls, interrupted, requested_ns, actual_ns;
    uint64_t max_actual_ns, max_requested_ns, max_start_ns, max_end_ns;
    uint64_t cpu_ns, voluntary_switches, involuntary_switches;
    uint64_t bins[8];
};

static int (*original_sleep)(const struct timespec *, struct timespec *);
static __thread int tracking;
static __thread struct sleep_trace trace;
static __thread struct rusage initial_usage;

__attribute__((constructor)) static void resolve_sleep(void)
{
    original_sleep = dlsym(RTLD_NEXT, "nanosleep");
}

static uint64_t monotonic_ns(void)
{
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (uint64_t)now.tv_sec * 1000000000ULL + now.tv_nsec;
}

static uint64_t cpu_ns(const struct rusage *usage)
{
    return ((uint64_t)usage->ru_utime.tv_sec + usage->ru_stime.tv_sec) * 1000000000ULL
        + ((uint64_t)usage->ru_utime.tv_usec + usage->ru_stime.tv_usec) * 1000ULL;
}

int gl_trace_ready(void)
{
    return original_sleep != NULL;
}

void gl_trace_begin(void)
{
    memset(&trace, 0, sizeof(trace));
    getrusage(RUSAGE_THREAD, &initial_usage);
    tracking = 1;
}

void gl_trace_end(struct sleep_trace *result)
{
    struct rusage final_usage;
    tracking = 0;
    getrusage(RUSAGE_THREAD, &final_usage);
    trace.cpu_ns = cpu_ns(&final_usage) - cpu_ns(&initial_usage);
    trace.voluntary_switches = final_usage.ru_nvcsw - initial_usage.ru_nvcsw;
    trace.involuntary_switches = final_usage.ru_nivcsw - initial_usage.ru_nivcsw;
    *result = trace;
}

int nanosleep(const struct timespec *request, struct timespec *remaining)
{
    if (original_sleep == NULL) {
        errno = ENOSYS;
        return -1;
    }
    if (!tracking)
        return original_sleep(request, remaining);
    uint64_t start = monotonic_ns();
    int result = original_sleep(request, remaining);
    int saved_errno = errno;
    uint64_t end = monotonic_ns();
    uint64_t elapsed = end - start;
    uint64_t requested = (uint64_t)request->tv_sec * 1000000000ULL + request->tv_nsec;
    unsigned bin = 0;
    const uint64_t limits[7] = {250000, 500000, 1000000, 2000000, 4000000, 8000000, 16000000};
    while (bin < 7 && elapsed > limits[bin])
        bin++;
    trace.bins[bin]++;
    trace.calls++;
    trace.interrupted += result == -1 && saved_errno == EINTR;
    trace.requested_ns += requested;
    trace.actual_ns += elapsed;
    if (elapsed > trace.max_actual_ns) {
        trace.max_actual_ns = elapsed;
        trace.max_requested_ns = requested;
        trace.max_start_ns = start;
        trace.max_end_ns = end;
    }
    errno = saved_errno;
    return result;
}
