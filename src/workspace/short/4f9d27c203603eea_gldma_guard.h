#ifndef GUARDIANLOOP_DMA_GUARD_H
#define GUARDIANLOOP_DMA_GUARD_H

#include "gldma_uapi.h"

#define GLDMA_GUARD_WORDS 8U
#define GLDMA_GUARD_BYTES (GLDMA_GUARD_WORDS * sizeof(__u64))
#define GLDMA_BUFFER_WORDS (GLDMA_WORDS + 2U * GLDMA_GUARD_WORDS)
#define GLDMA_BUFFER_BYTES (GLDMA_BUFFER_WORDS * sizeof(__u64))
#define GLDMA_TX_TAG 0x54580000ULL
#define GLDMA_RX_TAG 0x52580000ULL

static inline __u64 gldma_canary(__u64 tag, unsigned int index)
{
	return 0x9e3779b97f4a7c15ULL ^ tag ^ ((__u64)index << 32);
}

static inline void gldma_guard_init(__u64 *buffer, __u64 tag)
{
	unsigned int i;

	for (i = 0; i < GLDMA_GUARD_WORDS; i++) {
		buffer[i] = gldma_canary(tag, i);
		buffer[GLDMA_GUARD_WORDS + GLDMA_WORDS + i] =
			gldma_canary(tag, i + GLDMA_GUARD_WORDS);
	}
}

static inline int gldma_guard_ok(const __u64 *buffer, __u64 tag)
{
	unsigned int i;

	for (i = 0; i < GLDMA_GUARD_WORDS; i++) {
		if (buffer[i] != gldma_canary(tag, i) ||
		    buffer[GLDMA_GUARD_WORDS + GLDMA_WORDS + i] !=
			gldma_canary(tag, i + GLDMA_GUARD_WORDS))
			return 0;
	}
	return 1;
}

#endif
