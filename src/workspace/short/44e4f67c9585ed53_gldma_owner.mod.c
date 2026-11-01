#include <linux/build-salt.h>
#include <linux/module.h>
#include <linux/vermagic.h>
#include <linux/compiler.h>

BUILD_SALT;

MODULE_INFO(vermagic, VERMAGIC_STRING);
MODULE_INFO(name, KBUILD_MODNAME);

__visible struct module __this_module
__section(.gnu.linkonce.this_module) = {
	.name = KBUILD_MODNAME,
	.init = init_module,
#ifdef CONFIG_MODULE_UNLOAD
	.exit = cleanup_module,
#endif
	.arch = MODULE_ARCH_INIT,
};

#ifdef CONFIG_RETPOLINE
MODULE_INFO(retpoline, "Y");
#endif

static const struct modversion_info ____versions[]
__used __section(__versions) = {
	{ 0x136a4a24, "module_layout" },
	{ 0xac759445, "no_llseek" },
	{ 0x80432967, "platform_driver_unregister" },
	{ 0xce3b3f4b, "__platform_driver_register" },
	{ 0x47763fff, "kmalloc_caches" },
	{ 0x9d669763, "memcpy" },
	{ 0x7f02188f, "__msecs_to_jiffies" },
	{ 0x7837dbbc, "try_module_get" },
	{ 0x3375510b, "mutex_lock_interruptible" },
	{ 0x37a0cba, "kfree" },
	{ 0xae353d77, "arm_copy_from_user" },
	{ 0x56e379d9, "kmem_cache_alloc" },
	{ 0x526c3a6c, "jiffies" },
	{ 0x12a38747, "usleep_range" },
	{ 0x8f678b07, "__stack_chk_guard" },
	{ 0xdecd0b29, "__stack_chk_fail" },
	{ 0xd586efb6, "_dev_info" },
	{ 0x3cb7a9a4, "misc_register" },
	{ 0x1b0939c, "dma_alloc_attrs" },
	{ 0x512c2d08, "dma_set_coherent_mask" },
	{ 0x89383c93, "dma_set_mask" },
	{ 0x4d3256e3, "devm_ioremap_resource" },
	{ 0x72ae92a5, "platform_get_resource_byname" },
	{ 0x87a6ec15, "of_property_read_variable_u32_array" },
	{ 0xe346f67a, "__mutex_init" },
	{ 0x5f754e5a, "memset" },
	{ 0xfa6fed3f, "dma_free_attrs" },
	{ 0x678724fb, "_dev_err" },
	{ 0xfe57ae87, "misc_deregister" },
	{ 0x51a910c0, "arm_copy_to_user" },
	{ 0x822137e2, "arm_heavy_mb" },
	{ 0x67ea780, "mutex_unlock" },
	{ 0xc271c3be, "mutex_lock" },
	{ 0xefd6cf06, "__aeabi_unwind_cpp_pr0" },
};

MODULE_INFO(depends, "");

MODULE_ALIAS("of:N*T*Cguardianloop,z15-filter-dma-owner-v1");
MODULE_ALIAS("of:N*T*Cguardianloop,z15-filter-dma-owner-v1C*");
