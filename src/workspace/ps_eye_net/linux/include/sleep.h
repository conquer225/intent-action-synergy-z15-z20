#ifndef Z15_LINUX_SLEEP_H
#define Z15_LINUX_SLEEP_H
/* Keep the vendor SCCB API, implemented as a bounded Linux busy wait. */
int z15_delay_us(unsigned useconds);
#define usleep z15_delay_us
unsigned sleep(unsigned seconds);
#endif
