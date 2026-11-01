/* Shared canary algorithm test. No claim about physical DMA or AXI bounds. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "gldma_guard.h"

int main(void)
{
	__u64 words[GLDMA_BUFFER_WORDS] = {0};
	unsigned int i;

	assert(GLDMA_BUFFER_BYTES == 768);
	assert(GLDMA_GUARD_BYTES == 64);
	for (i = 0; i < 2; i++) {
		__u64 tag = i ? GLDMA_RX_TAG : GLDMA_TX_TAG;
		unsigned int j;
		gldma_guard_init(words, tag);
		memset(words + GLDMA_GUARD_WORDS, 0x55, GLDMA_FRAME_BYTES);
		assert(gldma_guard_ok(words, tag));
		assert(!gldma_guard_ok(words, tag ^ 1));
		for (j = 0; j < GLDMA_GUARD_WORDS; j++) {
			unsigned int tail = GLDMA_GUARD_WORDS + GLDMA_WORDS + j;
			words[j] ^= 1;
			assert(!gldma_guard_ok(words, tag));
			words[j] ^= 1;
			words[tail] ^= 1;
			assert(!gldma_guard_ok(words, tag));
			words[tail] ^= 1;
			assert(gldma_guard_ok(words, tag));
		}
	}
	puts("GLDMA_GUARD_HOST_PASS");
	return 0;
}
