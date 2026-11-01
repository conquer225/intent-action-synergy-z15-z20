`timescale 1ns/1ps
module z15_screen_top(input wire sys_clk,reset_n,
 input wire cam_pclk,cam_vsync,cam_href,input wire [7:0] cam_data,
 output wire cam_reset_n,cam_pwdn,cam_scl,inout wire cam_sda,
 input wire uart_rx,output wire uart_tx,output wire [1:0] led,
 output wire [2:0] hdmi_data_p,hdmi_data_n,output wire hdmi_clk_p,hdmi_clk_n);
 wire rst;reset_sync sys_reset(sys_clk,!reset_n,rst);
 wire ready,fault;wire [15:0] chip_id;
 camera_init init_i(sys_clk,rst,cam_scl,cam_sda,cam_reset_n,cam_pwdn,ready,fault,chip_id);
 wire pclk;BUFG cam_buf(.I(cam_pclk),.O(pclk));
 wire cam_rst;reset_sync camera_reset(pclk,rst,cam_rst);
 (* ASYNC_REG="TRUE" *) reg [1:0] ready_cam;
 always @(posedge pclk)if(cam_rst)ready_cam<=0;else ready_cam<={ready_cam[0],ready};
 wire push,full,empty,wr_busy,rd_busy;wire [29:0] camera_word,stream;
 screen_capture capture_i(pclk,cam_rst,ready_cam[1],cam_vsync,cam_href,cam_data,full||wr_busy,push,camera_word);
 wire word_valid=!empty&&!rd_busy;
 xpm_fifo_async #(.FIFO_MEMORY_TYPE("block"),.FIFO_WRITE_DEPTH(1024),.WRITE_DATA_WIDTH(30),.READ_DATA_WIDTH(30),
  .READ_MODE("fwft"),.FIFO_READ_LATENCY(0),.CDC_SYNC_STAGES(2),.DOUT_RESET_VALUE("0"),
  .ECC_MODE("no_ecc"),.PROG_EMPTY_THRESH(10),.PROG_FULL_THRESH(1010),.RD_DATA_COUNT_WIDTH(11),
  .WR_DATA_COUNT_WIDTH(11),.RELATED_CLOCKS(0),.SIM_ASSERT_CHK(1),.USE_ADV_FEATURES("0000"),.WAKEUP_TIME(0)) fifo_i(
  .rst(cam_rst),.wr_clk(pclk),.wr_en(push&&!full&&!wr_busy),.din(camera_word),.full(full),.wr_rst_busy(wr_busy),
  .rd_clk(sys_clk),.rd_en(word_valid),.dout(stream),.empty(empty),.rd_rst_busy(rd_busy),
  .sleep(1'b0),.injectdbiterr(1'b0),.injectsbiterr(1'b0));
 wire [50:0] roi0,roi1;wire [1:0] configured;
 wire start,preview,clear,config_changed;wire [1:0] es,ev;
 wire [7:0] ratio0,ratio1,q0,q1;wire [9:0] refx0,refx1;wire [8:0] refy0,refy1;
 wire [15:0] dark0,dark1;
 relative_eye eye0(sys_clk,rst,config_changed,word_valid,stream,roi0[50:41],roi0[40:32],roi0[31:24],roi0[23:16],roi0[15:8],roi0[7:0],es[0],ev[0],ratio0,refx0,refy0,dark0,q0);
 relative_eye eye1(sys_clk,rst,config_changed,word_valid,stream,roi1[50:41],roi1[40:32],roi1[31:24],roi1[23:16],roi1[15:8],roi1[7:0],es[1],ev[1],ratio1,refx1,refy1,dark1,q1);
 reg [1:0] pending;reg sample;
 always @(posedge sys_clk)begin
  sample<=0;
  if(rst||config_changed)pending<=0;
  else if((pending|es)==3)begin sample<=1;pending<=0;end
  else pending<=pending|es;
 end
 wire snapshot_request,snapshot_release,snapshot_ready,snapshot_busy;
 wire [16:0] snapshot_addr,display_addr;wire [7:0] snapshot_data,display_data;
 wire [2:0] mode,calibrated;wire [1:0] direction,event_direction;
 wire valid,stale,settled,armed,commit;wire [4:0] cal_count;wire [3:0] reason,progress;
 wire [15:0] event_seq;wire [7:0] l0,c0,r0,l1,c1,r1;
 screen_control gaze_i(sys_clk,rst,clear||config_changed,start,preview,sample,ready,snapshot_busy||snapshot_request,
  ev,ratio0,ratio1,refx0,refx1,refy0,refy1,mode,settled,cal_count,calibrated,direction,valid,stale,
  reason,progress,armed,commit,event_seq,event_direction,l0,c0,r0,l1,c1,r1);
 screen_serial serial_i(sys_clk,rst,uart_rx,uart_tx,direction,ev,event_direction,valid,stale,ready,fault,settled,armed,
  mode,calibrated,cal_count,reason,progress,ratio0,ratio1,event_seq,chip_id,start,preview,clear,config_changed,
  roi0,roi1,configured,snapshot_request,snapshot_ready,snapshot_release,snapshot_addr,snapshot_data);
 wire pix_clk,pix_clk5,locked,pix_rst;
 display_clocks #(.MULT_MASTER(63.0),.DIV_MASTER(5),.DIV_5X(5.0),.DIV_1X(25),.IN_PERIOD(20.0)) clocks_i(sys_clk,rst,pix_clk,pix_clk5,locked);
 reset_sync display_reset(pix_clk,!locked,pix_rst);
 // Half-size diagnostic image; all VGA pixels still reach the eye engines.
 wire reduced_valid=word_valid&&(stream[29]||(!stream[18]&&!stream[9]));
 wire [27:0] reduced={stream[29:28],stream[27:19],stream[17:10],1'b0,stream[7:0]};
 frame_store frames_i(sys_clk,rst,reduced_valid,reduced,snapshot_request,snapshot_release,snapshot_ready,snapshot_busy,
  snapshot_addr,snapshot_data,pix_clk,display_addr,display_data);
 wire [127:0] display_control;
 visual_mailbox #(.WIDTH(128)) visual_i(sys_clk,rst,{roi0,roi1,mode,direction,ev,event_direction,valid,ready,settled,armed,cal_count,reason,progress},pix_clk,pix_rst,display_control);
 screen_display display_i(pix_clk,pix_clk5,pix_rst,display_data,display_control,display_addr,hdmi_data_p,hdmi_data_n,hdmi_clk_p,hdmi_clk_n);
 // Z15 base-board S8050 LED drivers are active high.
 assign led={valid,ready};
endmodule
