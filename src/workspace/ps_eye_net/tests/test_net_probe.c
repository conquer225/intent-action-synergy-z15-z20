#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../tools/board_bridge.c"
static void local_progress(void){
    board_init();board.source=NET_SOURCE_LOCAL;
    board.eye.calibration_mask=3;board.eye.calibration_stage=3;
    board.eye.calibration_count[0]=5;board.eye.calibration_count[1]=7;
    board.eye.calibration[0][0]=32;board.eye.calibration[0][1]=128;
}
static void assert_progress(void){
    assert(board.source==NET_SOURCE_LOCAL&&board.eye.calibration_mask==3&&board.eye.calibration_stage==3);
    assert(board.eye.calibration_count[0]==5&&board.eye.calibration_count[1]==7);
    assert(board.eye.calibration[0][0]==32&&board.eye.calibration[0][1]==128);
}
int main(void){
    u8 *image=calloc(1,1280u*720u*3u),*pixels=malloc(NET_MAX_IMAGE),meta[60],reply[104],result[80]={0};
    assert(image&&pixels);
    NetFrame window;EyeFaceBox tiny={0,0,32,32,1};
    board_init();board.crop_face=tiny;
    assert(net_crop(image,3840,1280,720,&tiny,pixels,&window));board.pending=window;
    board.last.valid=1;board.last.face=(EyeFaceBox){0,0,1280,720,1};board.last_result_ms=1000;
    assert(net_control_crop(&board,image,3840,1280,720,1001,pixels,&window));
    assert(window.w==1280&&window.h==720); /* growing face can't underflow the inset bound */
    local_progress();
    assert(board_probe_prepare(image,1280u*720u*3u,1000,7,9,meta,pixels)>0);
    assert_progress();assert(!(net_u32(meta+40)&NET_ANCHORED));
    assert(board_probe_timeout(1221)&&!board_probe_promote(1221));
    board_pause();assert_progress();
    assert(board_probe_prepare(image,1280u*720u*3u,1400,8,9,meta,pixels)>0);
    assert(net_encode(reply,NET_RESULT,9,8,1400,result,80)==104);
    assert(board_probe_packet(reply,104,1410));assert_progress();
    assert(board_probe_promote(1420));
    assert(board.source==NET_SOURCE_PC&&!board.eye.calibration_mask&&!board.eye.calibration_stage&&!board.eye.valid);
    assert(board.accepted==1&&!board_probe_promote(1421));
    local_progress();
    assert(board_probe_prepare(image,1280u*720u*3u,1600,9,9,meta,pixels)>0);
    net_encode(reply,NET_RESULT,9,9,1600,result,80);
    assert(board_probe_packet(reply,104,1610));assert(!board_probe_promote(1821));assert_progress();
    assert(board_probe_prepare(image,1280u*720u*3u,2000,10,9,meta,pixels)>0);
    assert(board_command('r',2001));assert(!board_probe_waiting()&&!board_probe_promote(2001));
    net_encode(reply,NET_RESULT,9,10,2000,result,80);assert(!board_probe_packet(reply,104,2002));
    free(image);free(pixels);
    puts("PASS PC recovery probe: failed/expired probes preserve LOCAL calibration, fresh result switches once, reset cancels (native C)");
    return 0;
}
