#include "net_transport.h"
#include "video_io.h"
#include "live_osd.h"
#include "xparameters.h"
#include "xil_exception.h"
#include "xscugic.h"
#include "xil_printf.h"
#include "netif/xadapter.h"
#include "lwip/init.h"
#include "lwip/udp.h"
#include "lwip/etharp.h"
#include "sleep.h"
#include <stdio.h>
#include <string.h>
static struct netif interface;
static struct udp_pcb *socket;
static ip_addr_t peer_ip;
static u16 peer_port;
static NetControl *control;
static u32 session,nonce,peer_ms,arp_ms,link_ms,status_seq,last_cmd,cmd_ok,tx_fail;
static int enabled,stopped;
static u8 image[NET_MAX_IMAGE],wire[NET_MTU];
static u32 new_session(void){
    /* Epoch changes on peer restart; exact endpoint/nonce is pinned until lease expiry. */
    static u32 epochs=0x15300930u;
    epochs=epochs*1664525u+1013904223u+video_now_ms();return epochs?epochs:1;
}
int net_transport_peer(void){return enabled&&peer_port&&(u32)(video_now_ms()-peer_ms)<NET_PEER_TIMEOUT&&!stopped;}
static int send_packet(u8 type,u32 seq,u32 sampled,const u8 *payload,u16 length){
    int n=net_encode(wire,type,session,seq,sampled,payload,length);
    if(!n||!net_transport_peer())return 0;
    struct pbuf *p=pbuf_alloc(PBUF_TRANSPORT,(u16)n,PBUF_RAM);
    if(!p){tx_fail++;return 0;}
    err_t rc=pbuf_take(p,wire,(u16)n);
    if(rc==ERR_OK)rc=udp_sendto(socket,p,&peer_ip,peer_port);
    pbuf_free(p);
    if(rc!=ERR_OK)tx_fail++;
    return rc==ERR_OK;
}
void net_transport_status(void){
    if(!net_transport_peer())return;
    char text[1100];EyeTracker *t=&control->eye;
    int n=snprintf(text,sizeof(text),
        "{\"nonce\":%lu,\"source\":\"%s\",\"pair\":%d,\"stable\":%d,\"cal\":%u,\"stage\":%u,\"failed\":%u,"
        "\"valid\":%u,\"dir\":%u,\"armed\":%u,\"dwell\":%lu,\"event\":%lu,\"sample\":%lu,"
        "\"nx\":[%u,%u],\"pupil\":[[%u,%u],[%u,%u]],\"eye_valid\":[%u,%u],"
        "\"counts\":[%u,%u],\"refs\":[[%u,%u,%u],[%u,%u,%u]],\"pause\":%u,\"track\":%u,"
        "\"error\":%u,\"retry\":%u,\"detect_ms\":%lu,\"period_ms\":%lu,\"accepted\":%lu,\"rejected\":%lu,"
        "\"timeouts\":%lu,\"tx_fail\":%lu,\"cmdseq\":%lu,\"cmdok\":%lu,\"cam_frames\":%lu,\"hdmi_frames\":%lu}",
        (unsigned long)nonce,control->source==NET_SOURCE_PC?"PC":"LOCAL",control->last.valid,control->stable,
        t->calibration_mask,t->calibration_stage,t->cal_failed,t->valid,t->direction,t->armed,
        (unsigned long)t->dwell_ms,(unsigned long)t->event_seq,(unsigned long)control->sequence,
        t->left.normalized_x,t->right.normalized_x,t->left.x,t->left.y,t->right.x,t->right.y,t->left.valid,t->right.valid,
        t->calibration_count[0],t->calibration_count[1],t->calibration[0][0],t->calibration[0][1],t->calibration[0][2],
        t->calibration[1][0],t->calibration[1][1],t->calibration[1][2],t->calibration_paused,t->tracking_reason,
        t->cal_failure_reason,t->cal_retry_stage,(unsigned long)control->detect_ms,(unsigned long)control->period_ms,
        (unsigned long)control->accepted,(unsigned long)control->rejected,(unsigned long)control->timeouts,
        (unsigned long)tx_fail,(unsigned long)last_cmd,(unsigned long)cmd_ok,
        (unsigned long)live_osd_camera_frames(),(unsigned long)live_osd_display_frames());
    if(n>0&&n<(int)sizeof(text))send_packet(NET_STATUS,++status_seq,video_now_ms(),(const u8*)text,(u16)n);
}
static void receive(void *arg,struct udp_pcb *pcb,struct pbuf *p,const ip_addr_t *addr,u16 port){
    (void)arg;(void)pcb;u8 data[NET_MTU];NetPacket msg;
    if(!p)return;
    u16 n=p->tot_len;
    int copied=n<=NET_MTU&&pbuf_copy_partial(p,data,n,0)==n;
    pbuf_free(p);
    if(!copied||!net_decode(data,n,&msg))return;
    u32 now=video_now_ms();
    int same=peer_port==port&&ip_addr_cmp(&peer_ip,addr);
    if(msg.type==NET_HELLO&&msg.size==4&&!msg.session){
        u32 requested=net_u32(msg.payload);
        if(!requested)return;
        if(net_transport_peer()&&(!same||requested!=nonce))return;
        if(!net_transport_peer()){
            ip_addr_copy(peer_ip,*addr);peer_port=port;nonce=requested;session=new_session();last_cmd=0;cmd_ok=0;
            net_control_reset(control);
            xil_printf("NET_PEER session=%08lx port=%u - calibration cleared\r\n",(unsigned long)session,port);
        }
        peer_ms=now;net_transport_status();return;
    }
    if(!net_transport_peer()||!same||msg.session!=session)return;
    if(msg.type==NET_RESULT){
        if(net_control_result(control,&msg,now))net_transport_status();
    }else if(msg.type==NET_COMMAND&&msg.size==1&&msg.sequence){
        if(msg.sequence==last_cmd){net_transport_status();return;}
        /* Signed half-range ordering also handles command sequence wrap. */
        if(last_cmd&&(s32)(msg.sequence-last_cmd)<=0)return;
        last_cmd=msg.sequence;cmd_ok=(u32)net_control_command(control,(char)msg.payload[0],now);
        net_transport_status();
    }
}
int net_transport_init(NetControl *c){
    control=c;
    Xil_ExceptionInit();
    if(XScuGic_DeviceInitialize(XPAR_SCUGIC_SINGLE_DEVICE_ID)!=XST_SUCCESS)return 0;
    Xil_ExceptionRegisterHandler(XIL_EXCEPTION_ID_IRQ_INT,(Xil_ExceptionHandler)XScuGic_DeviceInterruptHandler,
                                (void*)XPAR_SCUGIC_SINGLE_DEVICE_ID);
    lwip_init();
    ip_addr_t ip,mask,gw;
    IP4_ADDR(&ip,192,168,1,10);IP4_ADDR(&mask,255,255,255,0);IP4_ADDR(&gw,192,168,1,1);
    unsigned char mac[]={0x02,0x15,0x00,0x00,0x00,0x10};
    if(!xemac_add(&interface,&ip,&mask,&gw,mac,XPAR_XEMACPS_0_BASEADDR))return 0;
    netif_set_default(&interface);netif_set_up(&interface);
    socket=udp_new();if(!socket)return 0;
    if(udp_bind(socket,IP_ADDR_ANY,NET_PORT)!=ERR_OK){udp_remove(socket);socket=0;return 0;}
    udp_recv(socket,receive,0);
    Xil_ExceptionEnableMask(XIL_EXCEPTION_IRQ);
    enabled=1;arp_ms=link_ms=video_now_ms();
    xil_printf("NET_READY ip=192.168.1.10 mask=255.255.255.0 port=5001 UDP v1 GEM0\r\n");return 1;
}
void net_transport_poll(void){
    if(!enabled||stopped)return;
    xemacif_input(&interface);u32 now=video_now_ms();
    if((u32)(now-arp_ms)>=5000u){etharp_tmr();arp_ms=now;}
    if((u32)(now-link_ms)>=1000u){eth_link_detect(&interface);link_ms=now;}
}
int net_transport_send_frame(const u8 *frame,u32 sampled,u32 seq){
    NetFrame f;u8 payload[NET_FRAME_META+NET_CHUNK];
    if(!net_transport_peer()||!net_control_crop(control,frame,VIDEO_STRIDE,VIDEO_W,VIDEO_H,sampled,image,&f))return 0;
    if(control->eye.calibration_mask||control->eye.calibration_stage||control->eye.cal_failed){
        f.flags|=NET_ANCHORED;f.anchor=control->anchor;
    }
    net_control_begin(control,&f,session,seq,sampled);
    for(u32 i=0;i<f.count;i++){
        u32 offset=i*NET_CHUNK,len=f.total-offset;if(len>NET_CHUNK)len=NET_CHUNK;
        f.index=(u16)i;f.offset=offset;net_frame_encode(payload,&f);memcpy(payload+NET_FRAME_META,image+offset,len);
        int sent=0;
        for(int attempt=0;attempt<4&&!sent;attempt++){
            sent=send_packet(NET_FRAME,seq,sampled,payload,(u16)(NET_FRAME_META+len));
            if(!sent){net_transport_poll();usleep(100);}
        }
        if(!sent||(u32)(video_now_ms()-sampled)>NET_RESULT_TIMEOUT){control->waiting=0;control->timeouts++;eye_tracker_pause(&control->eye,EYE_PAUSE_TIMING);return 0;}
        if((i&7)==7){net_transport_poll();usleep(100);}
        /* A reset/calibration command invalidates the pending frame atomically. */
        if(!control->waiting)return control->have_sample&&control->last_sample_ms==sampled;
    }
    return 1;
}
void net_transport_stop(void){
    if(enabled&&socket){udp_remove(socket);socket=0;}
    stopped=1;enabled=0;peer_port=0;
}
