/* Host ABI check only. This program cannot access board hardware. */
#include <assert.h>
#include <stddef.h>
#include <stdio.h>

#include "gldma_uapi.h"

int main(void)
{
	assert(sizeof(struct gldma_frame) == 1288);
	assert(offsetof(struct gldma_frame, tx) == 8);
	assert(offsetof(struct gldma_frame, rx) == 648);
	assert(sizeof(struct gldma_status) == 32);
	assert(GLDMA_IOCTL_RUN == 0xc5084701UL);
	assert(GLDMA_IOCTL_STATUS == 0x80204702UL);
	assert(GLDMA_IOCTL_RESET_FILTER == 0x4703UL);
	printf("GLDMA_ABI_OK frame=%zu status=%zu run=%#lx status_ioctl=%#lx reset=%#lx\n",
	       sizeof(struct gldma_frame), sizeof(struct gldma_status),
	       (unsigned long)GLDMA_IOCTL_RUN,
	       (unsigned long)GLDMA_IOCTL_STATUS,
	       (unsigned long)GLDMA_IOCTL_RESET_FILTER);
	return 0;
}
