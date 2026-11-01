#ifndef GUARDIANLOOP_DMA_POLICY_H
#define GUARDIANLOOP_DMA_POLICY_H

#include "gldma_uapi.h"

/* Small dependency-free state machine shared with the offline host test.
 * The kernel implementation retains physical pages independently of this
 * policy; this header alone is not crash-safe memory ownership. */
static inline int gldma_policy_begin(__u32 *state)
{
	if (*state != GLDMA_READY)
		return 0;
	*state = GLDMA_RUNNING;
	return 1;
}

static inline void gldma_policy_finish(__u32 *state, int verified)
{
	if (*state != GLDMA_RUNNING) {
		*state = GLDMA_UNKNOWN;
		return;
	}
	*state = verified ? GLDMA_READY : GLDMA_UNKNOWN;
}

static inline void gldma_policy_release(__u32 *state, int ever_started)
{
	if (ever_started)
		*state = GLDMA_UNKNOWN;
}

/* A completed frame that cannot be delivered has no trustworthy consumer
 * checkpoint. Do not allow a second, stateful frame from that ambiguity. */
static inline void gldma_policy_delivery_failed(__u32 *state)
{
	*state = GLDMA_UNKNOWN;
}

#endif
