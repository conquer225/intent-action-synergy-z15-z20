// SPDX-License-Identifier: GPL-2.0-only
/* Isolated first-party candidate. Do not install or load on the live Z15. */
#include <linux/delay.h>
#include <linux/dma-mapping.h>
#include <linux/fs.h>
#include <linux/ioport.h>
#include <linux/io.h>
#include <linux/jiffies.h>
#include <linux/kernel.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/sched.h>
#include <linux/slab.h>
#include <linux/uaccess.h>

#include "gldma_uapi.h"
#include "gldma_policy.h"
#include "gldma_guard.h"

#define RESOURCE_BYTES 0x10000U
#define HP0_DDR_LIMIT 0x40000000ULL
#ifdef GLDMA_COEXIST
#define CANDIDATE_DMA_BASE 0x40410000ULL
#else
#define CANDIDATE_DMA_BASE 0x40400000ULL
#endif
#define CANDIDATE_GPIO_BASE 0x41200000ULL
#define FILTER_SIGNATURE 0x50460000U
#define FILTER_STATUS_MASK 0xfffffffcU
#define DMA_RESET 0x4U
#define DMA_HALTED 0x1U
#define DMA_IDLE 0x2U
#define DMA_RUN 0x1U
#define DMA_IOC 0x1000U
#define DMA_ERRORS 0x770U
#define DMA_CLEAR_IRQ 0x7000U

struct gldma_device {
	struct platform_device *pdev;
	struct miscdevice misc;
	struct mutex lock;
	void __iomem *dma_regs;
	void __iomem *gpio_regs;
	void *tx;
	void *rx;
	dma_addr_t tx_bus;
	dma_addr_t rx_bus;
	u32 state;
	bool opened;
	bool ever_started;
	bool initialized;
	pid_t owner_tgid;
};

static struct gldma_device owner;
static atomic_t owner_claimed = ATOMIC_INIT(0);

static u32 dma_read(u32 offset)
{
	return readl(owner.dma_regs + offset);
}

static void dma_write(u32 offset, u32 value)
{
	writel(value, owner.dma_regs + offset);
}

static u32 gpio_read(u32 offset)
{
	return readl(owner.gpio_regs + offset);
}

static void gpio_write(u32 offset, u32 value)
{
	writel(value, owner.gpio_regs + offset);
}

static int wait_dma_mask(u32 offset_a, u32 offset_b, u32 mask,
			 bool set, unsigned long deadline)
{
	for (;;) {
		u32 a = dma_read(offset_a);
		u32 b = dma_read(offset_b);

		if (set ? ((a & mask) && (b & mask)) :
			  (!(a & mask) && !(b & mask)))
			return 0;
		if (time_after_eq(jiffies, deadline))
			return -ETIMEDOUT;
		usleep_range(100, 200);
	}
}

static int filter_status_ok(void)
{
	return gpio_read(0x08) == FILTER_SIGNATURE;
}

static int wait_filter_status(u32 expected, unsigned long deadline)
{
	for (;;) {
		if (gpio_read(0x08) == expected)
			return 0;
		if (time_after_eq(jiffies, deadline))
			return -ETIMEDOUT;
		usleep_range(100, 200);
	}
}

static int prepare_channels(unsigned long deadline)
{
	int ret;

	if ((gpio_read(0x08) & FILTER_STATUS_MASK) != FILTER_SIGNATURE)
		return -ENODEV;

	/* Only the first, proven-idle session may reset the DMA. This is never
	 * called after a timeout, process crash, or UNKNOWN state. */
	dma_write(0x00, DMA_RESET);
	ret = wait_dma_mask(0x00, 0x30, DMA_RESET, false, deadline);
	if (ret)
		return ret;
	ret = wait_dma_mask(0x04, 0x34, DMA_HALTED, true, deadline);
	if (ret)
		return ret;

	gpio_write(0x04, 0);         /* GPIO channel 1: filter reset output */
	gpio_write(0x0c, 0xffffffff); /* GPIO channel 2: status input */
	gpio_write(0x00, 1);
	ret = wait_filter_status(FILTER_SIGNATURE | 1, deadline);
	if (ret)
		return ret;
	gpio_write(0x00, 0);
	ret = wait_filter_status(FILTER_SIGNATURE, deadline);
	if (ret)
		return ret;

	dma_write(0x00, DMA_RUN);
	dma_write(0x30, DMA_RUN);
	return wait_dma_mask(0x04, 0x34, DMA_HALTED, false, deadline);
}

static int wait_frame(unsigned long deadline)
{
	for (;;) {
		u32 mm2s = dma_read(0x04);
		u32 s2mm = dma_read(0x34);

		if ((mm2s | s2mm) & DMA_ERRORS || !filter_status_ok() ||
		    (mm2s | s2mm) & DMA_HALTED)
			return -EIO;
		if ((mm2s & (DMA_IOC | DMA_IDLE)) == (DMA_IOC | DMA_IDLE) &&
		    (s2mm & (DMA_IOC | DMA_IDLE)) == (DMA_IOC | DMA_IDLE)) {
			if (dma_read(0x58) != GLDMA_FRAME_BYTES)
				return -EIO;
			return 0;
		}
		if (time_after_eq(jiffies, deadline))
			return -ETIMEDOUT;
		usleep_range(100, 200);
	}
}

static int gldma_run(struct gldma_frame *frame)
{
	unsigned long deadline;
	int ret;
	u32 i;

	if (frame->version != GLDMA_ABI_VERSION || !frame->timeout_ms ||
	    frame->timeout_ms > 1000)
		return -EINVAL;
	for (i = 0; i < GLDMA_WORDS; i++) {
		if (frame->tx[i] < -(1LL << 39) ||
		    frame->tx[i] > ((1LL << 39) - 1))
			return -ERANGE;
	}
	if (!owner.dma_regs || !owner.gpio_regs)
		return -ENODEV;
	if (owner.state != GLDMA_READY)
		return -EUCLEAN;
	/* Reject an absent/wrong filter before permanently pinning the module.
	 * The later check in prepare_channels still guards the register sequence. */
	if (!owner.ever_started &&
	    (gpio_read(0x08) & FILTER_STATUS_MASK) != FILTER_SIGNATURE)
		return -ENODEV;

	/* This extra module reference intentionally survives normal file close.
	 * There is no unload path after the first DMA start in this candidate;
	 * only a verified PS/HP recovery design may introduce one. */
	if (!owner.ever_started) {
		if (!try_module_get(THIS_MODULE))
			return -ENODEV;
		owner.ever_started = true;
	}
	if (!gldma_policy_begin(&owner.state))
		return -EUCLEAN;
	deadline = jiffies + msecs_to_jiffies(frame->timeout_ms);

	if (!owner.initialized) {
		ret = prepare_channels(deadline);
		if (ret)
			goto unknown;
		owner.initialized = true;
	} else if (!filter_status_ok() ||
		   !(dma_read(0x04) & DMA_IDLE) ||
		   !(dma_read(0x34) & DMA_IDLE)) {
		ret = -EIO;
		goto unknown;
	}
	/* Canary memory is separate from the 640-byte DMA payload. Never refresh
	 * guards between frames: that would hide a late/out-of-bounds write. */
	rmb();
	if (!gldma_guard_ok(owner.tx, GLDMA_TX_TAG) ||
	    !gldma_guard_ok(owner.rx, GLDMA_RX_TAG)) {
		ret = -EOVERFLOW;
		goto unknown;
	}
	memcpy(owner.tx + GLDMA_GUARD_BYTES, frame->tx, GLDMA_FRAME_BYTES);
	/* A short/stale receive cannot silently reuse a previous valid frame. */
	memset(owner.rx + GLDMA_GUARD_BYTES, 0xa5, GLDMA_FRAME_BYTES);
	wmb();
	dma_write(0x04, DMA_CLEAR_IRQ);
	dma_write(0x34, DMA_CLEAR_IRQ);
	dma_write(0x48, (u32)(owner.rx_bus + GLDMA_GUARD_BYTES));
	dma_write(0x4c, 0);
	dma_write(0x58, GLDMA_FRAME_BYTES); /* Receive before transmit. */
	dma_write(0x18, (u32)(owner.tx_bus + GLDMA_GUARD_BYTES));
	dma_write(0x1c, 0);
	dma_write(0x28, GLDMA_FRAME_BYTES);
	ret = wait_frame(deadline);
	if (ret)
		goto unknown;
	rmb();
	if (!gldma_guard_ok(owner.tx, GLDMA_TX_TAG) ||
	    !gldma_guard_ok(owner.rx, GLDMA_RX_TAG)) {
		ret = -EOVERFLOW;
		goto unknown;
	}
	memcpy(frame->rx, owner.rx + GLDMA_GUARD_BYTES, GLDMA_FRAME_BYTES);
	for (i = 0; i < GLDMA_WORDS; i++) {
		if (frame->rx[i] < -(1LL << 39) ||
		    frame->rx[i] > ((1LL << 39) - 1)) {
			ret = -EIO;
			goto unknown;
		}
	}
	gldma_policy_finish(&owner.state, 1);
	return 0;

unknown:
	/* No DMA reset, no buffer free, no retry from this boot session. */
	gldma_policy_finish(&owner.state, 0);
	return ret;
}

/* A discontinuity may reset only the filter state after a fully delivered
 * frame. This neither resets DMA nor releases its pinned buffers. UNKNOWN
 * ownership still requires full PS/HP recovery. */
#ifdef GLDMA_COEXIST
static int gldma_reset_filter(void)
{
	unsigned long deadline = jiffies + msecs_to_jiffies(100);
	int ret;

	if (owner.state != GLDMA_READY || !owner.initialized ||
	    !owner.ever_started)
		return -EUCLEAN;
	if (!filter_status_ok() || !(dma_read(0x04) & DMA_IDLE) ||
	    !(dma_read(0x34) & DMA_IDLE)) {
		owner.state = GLDMA_UNKNOWN;
		return -EIO;
	}
	gpio_write(0x00, 1);
	ret = wait_filter_status(FILTER_SIGNATURE | 1, deadline);
	if (!ret) {
		gpio_write(0x00, 0);
		ret = wait_filter_status(FILTER_SIGNATURE, deadline);
	}
	if (ret)
		owner.state = GLDMA_UNKNOWN;
	return ret;
}
#endif

static long gldma_ioctl(struct file *file, unsigned int command,
			unsigned long argument)
{
	void __user *arg = (void __user *)argument;
	struct gldma_frame *frame;
	struct gldma_status status;
	int ret;

	if (command == GLDMA_IOCTL_STATUS) {
		mutex_lock(&owner.lock);
		status.version = GLDMA_ABI_VERSION;
		status.state = owner.state;
		status.ever_started = owner.ever_started;
		status.reserved = 0;
		status.tx_dma_address = owner.tx ? owner.tx_bus + GLDMA_GUARD_BYTES : 0;
		status.rx_dma_address = owner.rx ? owner.rx_bus + GLDMA_GUARD_BYTES : 0;
		mutex_unlock(&owner.lock);
		return copy_to_user(arg, &status, sizeof(status)) ? -EFAULT : 0;
	}
#ifdef GLDMA_COEXIST
	if (command == GLDMA_IOCTL_RESET_FILTER) {
		if (!(file->f_mode & FMODE_WRITE))
			return -EPERM;
		ret = mutex_lock_interruptible(&owner.lock);
		if (ret)
			return ret;
		ret = owner.owner_tgid == task_tgid_nr(current) ?
			gldma_reset_filter() : -EPERM;
		mutex_unlock(&owner.lock);
		return ret;
	}
#endif
	if (command != GLDMA_IOCTL_RUN)
		return -ENOTTY;
	if (!(file->f_mode & FMODE_WRITE))
		return -EPERM;
	frame = kzalloc(sizeof(*frame), GFP_KERNEL);
	if (!frame)
		return -ENOMEM;
	if (copy_from_user(frame, arg, sizeof(*frame))) {
		ret = -EFAULT;
		goto out;
	}
	ret = mutex_lock_interruptible(&owner.lock);
	if (ret)
		goto out;
	if (owner.owner_tgid != task_tgid_nr(current))
		ret = -EPERM;
	else
		ret = gldma_run(frame);
	/* Delivery is part of the same transaction. Another thread sharing this
	 * fd must not start the next frame before the result reaches userspace. */
	if (!ret && copy_to_user(arg, frame, sizeof(*frame))) {
		gldma_policy_delivery_failed(&owner.state);
		ret = -EFAULT;
	}
	mutex_unlock(&owner.lock);
out:
	kfree(frame);
	return ret;
}

static int gldma_open(struct inode *inode, struct file *file)
{
	int ret = 0;

	mutex_lock(&owner.lock);
	if (owner.opened)
		ret = -EBUSY;
	else {
		owner.opened = true;
		owner.owner_tgid = task_tgid_nr(current);
	}
	mutex_unlock(&owner.lock);
	return ret;
}

static int gldma_release(struct inode *inode, struct file *file)
{
	mutex_lock(&owner.lock);
	/* A restarted worker cannot reconstruct its prior filter origin/state.
	 * Keep the pages but refuse another session until a verified recovery
	 * protocol exists. The same open fd can process multiple frames. */
	gldma_policy_release(&owner.state, owner.ever_started);
	owner.opened = false;
	owner.owner_tgid = 0;
	mutex_unlock(&owner.lock);
	return 0;
}

static const struct file_operations gldma_fops = {
	.owner = THIS_MODULE,
	.open = gldma_open,
	.release = gldma_release,
	.unlocked_ioctl = gldma_ioctl,
	.llseek = no_llseek,
};

static int gldma_probe(struct platform_device *pdev)
{
	struct resource *dma_resource, *gpio_resource;
	struct device *dev = &pdev->dev;
	u32 abi_version;
	int ret;

	if (atomic_cmpxchg(&owner_claimed, 0, 1))
		return -EBUSY;
	memset(&owner, 0, sizeof(owner));
	mutex_init(&owner.lock);
	owner.pdev = pdev;
	if (of_property_read_u32(dev->of_node, "guardianloop,abi-version",
				 &abi_version) || abi_version != GLDMA_ABI_VERSION) {
		ret = -EINVAL;
		goto release_claim;
	}
	dma_resource = platform_get_resource_byname(pdev, IORESOURCE_MEM, "dma");
	gpio_resource = platform_get_resource_byname(pdev, IORESOURCE_MEM,
					      "control");
	/* Fail closed if the device tree does not match the isolated BD. */
	if (!dma_resource || !gpio_resource ||
	    dma_resource->start != CANDIDATE_DMA_BASE ||
	    gpio_resource->start != CANDIDATE_GPIO_BASE ||
	    resource_size(dma_resource) != RESOURCE_BYTES ||
	    resource_size(gpio_resource) != RESOURCE_BYTES) {
		ret = -EINVAL;
		goto release_claim;
	}
	owner.dma_regs = devm_ioremap_resource(dev, dma_resource);
	if (IS_ERR(owner.dma_regs)) {
		ret = PTR_ERR(owner.dma_regs);
		goto release_claim;
	}
	owner.gpio_regs = devm_ioremap_resource(dev, gpio_resource);
	if (IS_ERR(owner.gpio_regs)) {
		ret = PTR_ERR(owner.gpio_regs);
		goto release_claim;
	}
	/* Do not invent a DMA mask for an unconfigured synthetic device. */
	ret = dma_set_mask_and_coherent(dev, DMA_BIT_MASK(32));
	if (ret)
		goto release_claim;
	owner.tx = dma_alloc_coherent(dev, GLDMA_BUFFER_BYTES,
				      &owner.tx_bus, GFP_KERNEL);
	if (!owner.tx) {
		ret = -ENOMEM;
		goto release_claim;
	}
	owner.rx = dma_alloc_coherent(dev, GLDMA_BUFFER_BYTES,
				      &owner.rx_bus, GFP_KERNEL);
	if (!owner.rx) {
		ret = -ENOMEM;
		goto free_tx;
	}
	/* The candidate BD maps both masters only to HP0_DDR_LOWOCM [0,1 GiB).
	 * A 32-bit DMA mask alone would allow addresses outside that segment. */
	if ((u64)owner.tx_bus > HP0_DDR_LIMIT - GLDMA_BUFFER_BYTES ||
	    (u64)owner.rx_bus > HP0_DDR_LIMIT - GLDMA_BUFFER_BYTES ||
	    !IS_ALIGNED((u64)owner.tx_bus, sizeof(__s64)) ||
	    !IS_ALIGNED((u64)owner.rx_bus, sizeof(__s64))) {
		ret = -ERANGE;
		goto free_rx;
	}
	gldma_guard_init(owner.tx, GLDMA_TX_TAG);
	gldma_guard_init(owner.rx, GLDMA_RX_TAG);
	owner.misc.minor = MISC_DYNAMIC_MINOR;
	owner.misc.name = "guardianloop_dma_keeper";
	owner.misc.fops = &gldma_fops;
	owner.misc.mode = 0600;
	owner.misc.parent = dev;
	ret = misc_register(&owner.misc);
	if (ret)
		goto free_rx;
	platform_set_drvdata(pdev, &owner);
	dev_info(dev, "isolated DMA owner bound; physical transfer not yet validated\n");
	return 0;

free_rx:
	dma_free_coherent(dev, GLDMA_BUFFER_BYTES, owner.rx, owner.rx_bus);
free_tx:
	dma_free_coherent(dev, GLDMA_BUFFER_BYTES, owner.tx, owner.tx_bus);
release_claim:
	atomic_set(&owner_claimed, 0);
	return ret;
}

static int gldma_remove(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	void *tx, *rx;
	dma_addr_t tx_bus, rx_bus;
	bool started;

	/* Device-core removal may ignore a negative return. Invalidate every
	 * surviving fd before devres unmaps registers, and never reuse this owner
	 * within the same module load after a successful probe. */
	mutex_lock(&owner.lock);
	started = owner.ever_started;
	owner.state = GLDMA_UNKNOWN;
	owner.dma_regs = NULL;
	owner.gpio_regs = NULL;
	tx = owner.tx;
	rx = owner.rx;
	tx_bus = owner.tx_bus;
	rx_bus = owner.rx_bus;
	if (!started) {
		owner.tx = NULL;
		owner.rx = NULL;
		owner.tx_bus = 0;
		owner.rx_bus = 0;
	}
	mutex_unlock(&owner.lock);
	misc_deregister(&owner.misc);
	if (started) {
		dev_err(dev, "device removed after DMA start; buffers retained and reuse forbidden\n");
		return -EBUSY;
	}
	dma_free_coherent(dev, GLDMA_BUFFER_BYTES, rx, rx_bus);
	dma_free_coherent(dev, GLDMA_BUFFER_BYTES, tx, tx_bus);
	platform_set_drvdata(pdev, NULL);
	return 0;
}

static const struct of_device_id gldma_of_match[] = {
	{ .compatible = "guardianloop,z15-filter-dma-owner-v1" },
	{ }
};
MODULE_DEVICE_TABLE(of, gldma_of_match);

static struct platform_driver gldma_driver = {
	.probe = gldma_probe,
	.remove = gldma_remove,
	.driver = {
		.name = "guardianloop-dma-owner",
		.of_match_table = gldma_of_match,
		.suppress_bind_attrs = true,
	},
};
module_platform_driver(gldma_driver);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("GuardianLoop isolated crash-persistent DMA buffer candidate");
