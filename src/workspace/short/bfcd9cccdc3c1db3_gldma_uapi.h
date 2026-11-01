#ifndef GUARDIANLOOP_DMA_UAPI_H
#define GUARDIANLOOP_DMA_UAPI_H

#include <linux/ioctl.h>
#include <linux/types.h>

#define GLDMA_ABI_VERSION 1U
#define GLDMA_WORDS 80U
#define GLDMA_FRAME_BYTES (GLDMA_WORDS * sizeof(__s64))

#define GLDMA_READY 0U
#define GLDMA_RUNNING 1U
#define GLDMA_UNKNOWN 2U

struct gldma_frame {
	__u32 version;
	__u32 timeout_ms;
	__s64 tx[GLDMA_WORDS];
	__s64 rx[GLDMA_WORDS];
};

struct gldma_status {
	__u32 version;
	__u32 state;
	__u32 ever_started;
	__u32 reserved;
	__u64 tx_dma_address;
	__u64 rx_dma_address;
};

#define GLDMA_IOCTL_RUN _IOWR('G', 1, struct gldma_frame)
#define GLDMA_IOCTL_STATUS _IOR('G', 2, struct gldma_status)
#define GLDMA_IOCTL_RESET_FILTER _IO('G', 3)

#endif
