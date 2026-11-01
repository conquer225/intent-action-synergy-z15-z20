/* Isolated future board test. No insmod, MMIO, reset or Overlay loading.
 * --check-vectors is host-only. Hardware modes require separate authorization. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include "gldma_uapi.h"
#include "gldma_guard.h"

#define DEVICE "/dev/guardianloop_dma_keeper"
#define WRAP_CANARY UINT64_C(0x12345abcde543210)

struct guarded_frame {
	uint64_t head;
	struct gldma_frame frame;
	uint64_t tail;
};

static int fail(const char *message)
{
	fprintf(stderr, "GLDMA_TEST_FAIL: %s (errno=%d)\n", message, errno);
	return -1;
}

static int read_frame(FILE *fp, struct gldma_frame *frame, int64_t *golden)
{
	if (fread(frame->tx, sizeof(frame->tx), 1, fp) != 1 ||
	    fread(golden, GLDMA_FRAME_BYTES, 1, fp) != 1)
		return fail("truncated vectors");
	return 0;
}

static int vectors_open(const char *path, FILE **fp, uint32_t *frames)
{
	char magic[8];
	uint32_t version;
	const uint16_t endian = 1;
	struct gldma_frame frame;
	int64_t golden[GLDMA_WORDS];
	uint32_t i, j;

	if (*(const unsigned char *)&endian != 1)
		return fail("vectors require a little-endian host");
	*fp = fopen(path, "rb");
	if (!*fp)
		return fail("open vectors");
	if (fread(magic, 8, 1, *fp) != 1 || memcmp(magic, "GLDMA001", 8) ||
	    fread(&version, sizeof(version), 1, *fp) != 1 || version != 1 ||
	    fread(frames, sizeof(*frames), 1, *fp) != 1 ||
	    *frames < 2 || *frames > 10000)
		return fail("invalid vector header");
	for (i = 0; i < *frames; i++) {
		if (read_frame(*fp, &frame, golden))
			return -1;
		for (j = 0; j < GLDMA_WORDS; j++) {
			if (frame.tx[j] < -(1LL << 39) || frame.tx[j] >= (1LL << 39) ||
			    golden[j] < -(1LL << 39) || golden[j] >= (1LL << 39))
				return fail("vector word exceeds signed40");
		}
	}
	if (fgetc(*fp) != EOF || ferror(*fp) || fseek(*fp, 16, SEEK_SET))
		return fail("trailing data or vector read error");
	return 0;
}

static int status_get(int fd, struct gldma_status *status)
{
	if (ioctl(fd, GLDMA_IOCTL_STATUS, status) || status->version != 1 ||
	    status->reserved || status->state > GLDMA_UNKNOWN)
		return fail("STATUS ABI");
	return 0;
}

static int fresh_owner(int fd, struct gldma_status *status)
{
	if (status_get(fd, status))
		return -1;
	if (status->state != GLDMA_READY || status->ever_started ||
	    status->tx_dma_address < GLDMA_GUARD_BYTES ||
	    status->rx_dma_address < GLDMA_GUARD_BYTES ||
	    status->tx_dma_address > 0x40000000ULL - GLDMA_FRAME_BYTES - GLDMA_GUARD_BYTES ||
	    status->rx_dma_address > 0x40000000ULL - GLDMA_FRAME_BYTES - GLDMA_GUARD_BYTES ||
	    status->tx_dma_address % 8 || status->rx_dma_address % 8 ||
	    status->tx_dma_address == status->rx_dma_address)
		return fail("not a fresh bounded owner; do not reset or retry");
	return 0;
}

static int expect_error(int fd, struct gldma_frame *frame, int expected)
{
	errno = 0;
	if (ioctl(fd, GLDMA_IOCTL_RUN, frame) != -1 || errno != expected)
		return fail("unexpected RUN error contract");
	return 0;
}

static int compare_run(int fd, struct gldma_frame *input, const int64_t *golden,
		       FILE *dump, double *ioctl_ms)
{
	struct guarded_frame wrap;
	struct timespec begin, end;
	uint32_t j;

	memset(&wrap, 0, sizeof(wrap));
	wrap.head = wrap.tail = WRAP_CANARY;
	wrap.frame = *input;
	wrap.frame.version = 1;
	wrap.frame.timeout_ms = 1000;
	if (ioctl_ms)
		clock_gettime(CLOCK_MONOTONIC, &begin);
	if (ioctl(fd, GLDMA_IOCTL_RUN, &wrap.frame))
		return fail("RUN; no reset/free/retry allowed on failure");
	if (ioctl_ms) {
		clock_gettime(CLOCK_MONOTONIC, &end);
		*ioctl_ms = (end.tv_sec - begin.tv_sec) * 1000.0 +
			(end.tv_nsec - begin.tv_nsec) / 1e6;
	}
	if (wrap.head != WRAP_CANARY || wrap.tail != WRAP_CANARY)
		return fail("userspace ioctl frame boundary overwritten");
	for (j = 0; j < GLDMA_WORDS; j++) {
		if (wrap.frame.rx[j] != golden[j]) {
			fprintf(stderr, "word=%u expected=%" PRId64 " actual=%" PRId64 "\n",
				j, golden[j], (int64_t)wrap.frame.rx[j]);
			return fail("bit-exact physical readback mismatch");
		}
	}
	if (dump && fwrite(wrap.frame.rx, GLDMA_FRAME_BYTES, 1, dump) != 1)
		return fail("write verified PL output");
	return 0;
}

static int compare_double(const void *left, const void *right)
{
	double a = *(const double *)left, b = *(const double *)right;
	return (a > b) - (a < b);
}

static int terminal_check(const struct gldma_status *before)
{
	struct gldma_status after;
	struct gldma_frame frame = {.version = 1, .timeout_ms = 1000};
	int fd = open(DEVICE, O_RDWR | O_CLOEXEC), result = -1;

	if (fd < 0)
		return fail("open terminal owner");
	if (!status_get(fd, &after) && after.state == GLDMA_UNKNOWN &&
	    after.ever_started == 1 && after.tx_dma_address == before->tx_dma_address &&
	    after.rx_dma_address == before->rx_dma_address &&
	    !expect_error(fd, &frame, EUCLEAN)) {
		printf("UNKNOWN_REUSE_REJECTED tx=0x%08" PRIx64 " rx=0x%08" PRIx64 "\n",
		       (uint64_t)after.tx_dma_address, (uint64_t)after.rx_dma_address);
		result = 0;
	} else {
		fail("terminal UNKNOWN or stable DMA address missing");
	}
	close(fd);
	return result;
}

static int admission_checks(int fd)
{
	struct gldma_frame frame = {.version = 1, .timeout_ms = 1000};
	struct gldma_status status;
	int second, result, child_status;
	pid_t child;

	errno = 0;
	second = open(DEVICE, O_RDWR | O_CLOEXEC);
	if (second >= 0) {
		close(second);
		return fail("concurrent open was allowed");
	}
	if (errno != EBUSY)
		return fail("concurrent open errno");
	frame.version = 2;
	result = expect_error(fd, &frame, EINVAL);
	frame.version = 1;
	frame.timeout_ms = 0;
	result |= expect_error(fd, &frame, EINVAL);
	frame.timeout_ms = 1001;
	result |= expect_error(fd, &frame, EINVAL);
	frame.timeout_ms = 1000;
	frame.tx[0] = 1LL << 39;
	result |= expect_error(fd, &frame, ERANGE);
	frame.tx[0] = 0;
	if (result || fresh_owner(fd, &status))
		return -1;
	child = fork();
	if (child < 0)
		return fail("fork");
	if (!child)
		_exit(expect_error(fd, &frame, EPERM) ? 1 : 0);
	if (waitpid(child, &child_status, 0) != child || !WIFEXITED(child_status) ||
	    WEXITSTATUS(child_status) || fresh_owner(fd, &status))
		return fail("inherited fd process identity");
	return 0;
}

static int run_all(FILE *fp, uint32_t frames, const char *dump_path)
{
	struct gldma_frame frame = {.version = 1, .timeout_ms = 1000};
	struct gldma_status before;
	int64_t golden[GLDMA_WORDS];
	struct timespec start, end;
	double elapsed;
	uint32_t i;
	FILE *dump = NULL;
	double *ioctl_ms = calloc(frames, sizeof(*ioctl_ms));
	int fd = open(DEVICE, O_RDONLY | O_CLOEXEC);
	int dump_fd;

	if (!ioctl_ms) {
		if (fd >= 0)
			close(fd);
		return fail("allocate timing samples");
	}

	if (dump_path) {
		dump_fd = open(dump_path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
		if (dump_fd < 0) {
			fail("create exclusive PL output file");
			goto bad;
		}
		dump = fdopen(dump_fd, "wb");
		if (!dump) {
			close(dump_fd);
			fail("open PL output stream");
			goto bad;
		}
	}

	if (fd < 0) {
		fail("open read-only owner");
		goto bad;
	}
	if (fresh_owner(fd, &before) || expect_error(fd, &frame, EPERM)) {
		goto bad;
	}
	close(fd); /* No RUN yet: this close must leave READY. */
	fd = -1;
	fd = open(DEVICE, O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		fail("open writable owner");
		goto bad;
	}
	if (fresh_owner(fd, &before) || admission_checks(fd))
		goto bad;
	clock_gettime(CLOCK_MONOTONIC, &start);
	for (i = 0; i < frames; i++) {
		struct gldma_status current;
		if (read_frame(fp, &frame, golden) ||
		    compare_run(fd, &frame, golden, dump, &ioctl_ms[i]) ||
		    status_get(fd, &current))
			goto bad;
		if (current.state != GLDMA_READY || current.ever_started != 1 ||
		    current.tx_dma_address != before.tx_dma_address ||
		    current.rx_dma_address != before.rx_dma_address) {
			fail("post-frame state/address");
			goto bad;
		}
	}
	clock_gettime(CLOCK_MONOTONIC, &end);
	elapsed = end.tv_sec - start.tv_sec + (end.tv_nsec - start.tv_nsec) / 1e9;
	if (dump && (fflush(dump) || fsync(fileno(dump))))
		goto bad;
	close(fd); /* Terminal by design; never reset for the next test. */
	fd = -1;
	if (terminal_check(&before))
		goto bad;
	if (dump && fclose(dump)) {
		free(ioctl_ms);
		return fail("close verified PL output");
	}
	dump = NULL;
	qsort(ioctl_ms, frames, sizeof(*ioctl_ms), compare_double);
	printf("GLDMA_PHYSICAL_FRAMES_PASS frames=%u words_per_frame=80 wall_s=%.6f\n",
	       frames, elapsed);
	printf("GLDMA_IOCTL_LATENCY_MS median=%.6f p95=%.6f max=%.6f\n",
	       ioctl_ms[frames / 2], ioctl_ms[(frames * 95 + 99) / 100 - 1],
	       ioctl_ms[frames - 1]);
	if (dump_path)
		printf("GLDMA_VERIFIED_OUTPUT path=%s bytes=%zu\n", dump_path,
		       (size_t)frames * GLDMA_FRAME_BYTES);
	free(ioctl_ms);
	return 0;
bad:
	if (fd >= 0)
		close(fd);
	if (dump)
		fclose(dump);
	free(ioctl_ms);
	return -1;
}

static int crash_after_completion(FILE *fp)
{
	struct gldma_status before;
	struct pollfd poller;
	int channel[2], child_status;
	pid_t child;
	ssize_t received;

	if (pipe(channel))
		return fail("pipe");
	child = fork();
	if (child < 0) {
		close(channel[0]); close(channel[1]);
		return fail("fork crash worker");
	}
	if (!child) {
		struct gldma_frame frame;
		int64_t golden[GLDMA_WORDS];
		int fd;
		close(channel[0]);
		fd = open(DEVICE, O_RDWR | O_CLOEXEC);
		if (fd < 0 || fresh_owner(fd, &before) ||
		    read_frame(fp, &frame, golden) || compare_run(fd, &frame, golden, NULL, NULL) ||
		    write(channel[1], &before, sizeof(before)) != sizeof(before))
			_exit(1);
		/* Keep the only owner fd alive until the parent sends SIGKILL. */
		for (;;) pause();
	}
	close(channel[1]);
	poller.fd = channel[0]; poller.events = POLLIN;
	if (poll(&poller, 1, 5000) <= 0)
		received = -1;
	else
		received = read(channel[0], &before, sizeof(before));
	close(channel[0]);
	if (kill(child, SIGKILL) && errno != ESRCH)
		return fail("kill worker");
	if (waitpid(child, &child_status, 0) != child || received != sizeof(before) ||
	    !WIFSIGNALED(child_status) || WTERMSIG(child_status) != SIGKILL)
		return fail("worker did not complete verified frame before SIGKILL");
	if (terminal_check(&before))
		return -1;
	puts("GLDMA_SIGKILL_AFTER_COMPLETION_PASS (not an in-flight kill test)");
	return 0;
}

int main(int argc, char **argv)
{
	FILE *fp = NULL;
	uint32_t frames;
	int result;

	if ((argc != 3 && argc != 4) || (strcmp(argv[1], "--check-vectors") &&
	    strcmp(argv[1], "--run-approved") &&
	    strcmp(argv[1], "--run-dump-approved") &&
	    strcmp(argv[1], "--crash-after-approved"))) {
		fprintf(stderr, "Usage: %s {--check-vectors|--run-approved|--crash-after-approved} golden_frames.bin\n"
			"       %s --run-dump-approved golden_frames.bin new_output.bin\n"
			"Hardware modes need separate authorization and a fresh, reviewed candidate boot.\n", argv[0], argv[0]);
		return 2;
	}
	if ((!strcmp(argv[1], "--run-dump-approved")) != (argc == 4))
		return 2;
	if (vectors_open(argv[2], &fp, &frames)) {
		if (fp) fclose(fp);
		return 1;
	}
	if (!strcmp(argv[1], "--check-vectors")) {
		printf("GLDMA_VECTOR_FORMAT_PASS frames=%u (no device opened)\n", frames);
		result = 0;
	} else if (!strcmp(argv[1], "--run-approved")) {
		result = run_all(fp, frames, NULL);
	} else if (!strcmp(argv[1], "--run-dump-approved")) {
		result = run_all(fp, frames, argv[3]);
	} else {
		result = crash_after_completion(fp);
	}
	fclose(fp);
	return result ? 1 : 0;
}
