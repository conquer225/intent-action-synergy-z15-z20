/* Native host test of the same state transitions compiled into the module.
 * It does not simulate AXI, DMA, kernel refcounts, or process-kill timing. */
#include <assert.h>
#include <stddef.h>
#include <stdio.h>

#include "gldma_policy.h"

int main(void)
{
	__u32 state = GLDMA_READY;

	assert(GLDMA_ABI_VERSION == 1);
	assert(GLDMA_FRAME_BYTES == 640);
	assert(sizeof(struct gldma_frame) == 1288);
	assert(offsetof(struct gldma_frame, tx) == 8);
	assert(offsetof(struct gldma_frame, rx) == 648);
	assert(sizeof(struct gldma_status) == 32);
	assert(gldma_policy_begin(&state));
	assert(state == GLDMA_RUNNING);
	assert(!gldma_policy_begin(&state));
	gldma_policy_finish(&state, 1);
	assert(state == GLDMA_READY);
	assert(gldma_policy_begin(&state));
	gldma_policy_finish(&state, 0);
	assert(state == GLDMA_UNKNOWN);
	assert(!gldma_policy_begin(&state));
	gldma_policy_finish(&state, 1);
	assert(state == GLDMA_UNKNOWN);
	gldma_policy_release(&state, 1);
	assert(state == GLDMA_UNKNOWN);
	state = GLDMA_READY;
	gldma_policy_release(&state, 1);
	assert(state == GLDMA_UNKNOWN);
	state = GLDMA_READY;
	gldma_policy_release(&state, 0);
	assert(state == GLDMA_READY);
	assert(gldma_policy_begin(&state));
	gldma_policy_finish(&state, 1);
	gldma_policy_delivery_failed(&state);
	assert(state == GLDMA_UNKNOWN);
	assert(!gldma_policy_begin(&state));
	puts("GLDMA_POLICY_HOST_PASS");
	return 0;
}
