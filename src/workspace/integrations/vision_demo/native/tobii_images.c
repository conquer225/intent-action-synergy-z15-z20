// SPDX-License-Identifier: MIT
// Reuses the pinned Apache-2.0 IS4 protocol adapter; no calibration operations.
#define main existing_probe_main
#include "is4-probe.c"
#undef main
#include <sys/file.h>
#include <fcntl.h>
#include <unistd.h>

int main(int argc,char **argv){
    if(argc!=2 || chdir(argv[1]))return 2;
    int lock=open("/run/lock/tobii_calibration.lock",O_CREAT|O_RDWR,0600);
    if(lock<0||flock(lock,LOCK_EX|LOCK_NB))return 3;
    umask(0077);signal(SIGINT,handle_signal);signal(SIGTERM,handle_signal);
    libusb_context *ctx=NULL;libusb_device_handle *device=NULL;
    struct parser parser={0};struct ttp_frame frame;uint32_t sequence=1;
    int claimed=0,err=libusb_init(&ctx),count=0;
    uint64_t next=0;
    if(err)goto done;
    device=libusb_open_device_with_vid_pid(ctx,TOBII_VID,TOBII_PID);
    if(!device){err=-4;goto done;}
    libusb_set_auto_detach_kernel_driver(device,1);
    err=libusb_claim_interface(device,0);if(err)goto done;claimed=1;
    err=libusb_control_transfer(device,0x41,0x41,0,0,NULL,0,1000);if(err<0)goto done;
    err=run_tobiifree_handshake(device,&parser,&sequence);if(err)goto done;
    err=send_subscribe(device,sequence++,STREAM_IMAGE_SECONDARY,"vision_images");if(err)goto done;
    // Resume tracking only. Never send calibration start/clear/point/compute/model writes.
    unsigned char resume[11]={0},packet[MAX_PACKET_BYTES];tlv_u32(resume+2,0);
    size_t len=build_frame(packet+ENVELOPE_SIZE,sequence++,0x0c1c,resume,sizeof(resume));
    memset(packet,0,4);put_le32(packet+4,(uint32_t)len);
    err=send_packet(device,packet,ENVELOPE_SIZE+len);if(err)goto done;
    while(!stop_requested){
        int rc=read_next_frame(device,&parser,&frame,100);
        if(rc<0){err=rc;break;}if(!rc)continue;
        if(frame.magic==TTP_MAGIC_NOTIFY && frame.op==STREAM_IMAGE_SECONDARY && monotonic_ns()>=next){
            struct image_frame image;char path[1024];
            if(decode_image_payload(frame.op,frame.payload,frame.plen,&image) &&
                !write_pgm_frame(".",&image,count,count%2,true,path,sizeof(path))){
                count++;next=monotonic_ns()+200000000ull;
            }
        }
    }
done:
    if(claimed)libusb_release_interface(device,0);
    if(device)libusb_close(device);
    if(ctx)libusb_exit(ctx);
    close(lock);
    return err<0?1:0;
}
