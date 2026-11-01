/* Read-only diagnostic for a separately authorized future board test.
 * This program never submits DMA or changes a register. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include "gldma_uapi.h"

int main(int argc, char **argv)
{
	struct gldma_status status = {0};
	const char *path = argc == 2 ? argv[1] : "/dev/guardianloop_dma_keeper";
	int fd;

	if (argc > 2) {
		fprintf(stderr, "usage: %s [device]\n", argv[0]);
		return 2;
	}
	fd = open(path, O_RDONLY | O_CLOEXEC);
	if (fd < 0) {
		perror("open");
		return 1;
	}
	if (ioctl(fd, GLDMA_IOCTL_STATUS, &status) < 0) {
		perror("GLDMA_IOCTL_STATUS");
		close(fd);
		return 1;
	}
	close(fd);
	if (status.version != GLDMA_ABI_VERSION || status.state > GLDMA_UNKNOWN) {
		fprintf(stderr, "unexpected owner ABI/state\n");
		return 1;
	}
	printf("state=%u ever_started=%u tx=0x%llx rx=0x%llx\n",
	       status.state, status.ever_started,
	       (unsigned long long)status.tx_dma_address,
	       (unsigned long long)status.rx_dma_address);
	return 0;
}
