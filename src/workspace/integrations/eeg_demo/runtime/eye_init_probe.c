/* Private initialization probe; use the installed framing, never subscribe images. */
#define main existing_probe_main
#include "is4-probe.c"
#undef main

int main(void) {
    libusb_context *ctx = NULL;
    libusb_device_handle *handle = NULL;
    struct parser parser = {0};
    struct ttp_frame frame;
    bool claimed = false, answered = false;
    int err = libusb_init(&ctx);
    if (err) return 1;
    handle = libusb_open_device_with_vid_pid(ctx, TOBII_VID, TOBII_PID);
    if (!handle) { libusb_exit(ctx); return 2; }
    libusb_set_auto_detach_kernel_driver(handle, 1);
    err = libusb_claim_interface(handle, TOBII_VENDOR_IFACE);
    if (err) goto done;
    claimed = true;
    err = libusb_control_transfer(handle, 0x41, 0x41, 0, 0, NULL, 0, 1000);
    printf("OPEN_CONTROL %d\n", err); fflush(stdout);
    if (err < 0) goto done;
    unsigned char request[512], incoming[READ_BUFFER_BYTES];
    size_t len = build_hello(1, request);
    err = send_packet(handle, request, len);
    printf("HELLO_SEND %d bytes=%zu\n", err, len); fflush(stdout);
    if (err) goto done;
    for (unsigned i = 0; i < 25 && !answered; ++i) {
        int received = 0;
        int rc = libusb_bulk_transfer(handle, TOBII_EP_IN, incoming, sizeof(incoming), &received, 100);
        if (received > 0) {
            printf("IN_TRANSFER rc=%d bytes=%d\n", rc, received); fflush(stdout);
            if (parser_feed(&parser, incoming, received)) { err = -8; break; }
            int parsed;
            while ((parsed = parser_pop(&parser, &frame)) > 0) {
                printf("FRAME magic=%02x op=%04x seq=%u status=%08x\n", frame.magic, frame.op, frame.seq, frame.status);
                answered = frame.magic == TTP_MAGIC_RSP && frame.op == TTP_OP_HELLO && frame.seq == 1;
            }
            if (parsed < 0) { err = -1; break; }
        }
        if (rc && rc != LIBUSB_ERROR_TIMEOUT) { err = rc; break; }
    }
    printf("HELLO_ANSWERED %s\n", answered ? "yes" : "no"); fflush(stdout);
done:
    if (claimed) {
        libusb_control_transfer(handle, 0x41, 0x42, 0, 0, NULL, 0, 500);
        libusb_release_interface(handle, TOBII_VENDOR_IFACE);
    }
    libusb_close(handle); libusb_exit(ctx);
    return err < 0 ? 3 : answered ? 0 : 4;
}
