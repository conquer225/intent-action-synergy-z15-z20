`timescale 1ns/1ps
module z15_eye_top(input wire sys_clk,reset_n,
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
 wire push,full,empty,wr_busy,rd_busy;wire [27:0] camera_word,stream;
 camera_capture capture_i(pclk,cam_rst,ready_cam[1],cam_vsync,cam_href,cam_data,full||wr_busy,push,camera_word);
 wire word_valid=!empty&&!rd_busy;
 xpm_fifo_async #(.FIFO_MEMORY_TYPE("block"),.FIFO_WRITE_DEPTH(1024),.WRITE_DATA_WIDTH(28),.READ_DATA_WIDTH(28),
  .READ_MODE("fwft"),.FIFO_READ_LATENCY(0),.CDC_SYNC_STAGES(2),.DOUT_RESET_VALUE("0"),
  .ECC_MODE("no_ecc"),.PROG_EMPTY_THRESH(10),.PROG_FULL_THRESH(1010),.RD_DATA_COUNT_WIDTH(11),
  .WR_DATA_COUNT_WIDTH(11),.RELATED_CLOCKS(0),.SIM_ASSERT_CHK(1),.USE_ADV_FEATURES("0000"),.WAKEUP_TIME(0)) fifo_i(
  .rst(cam_rst),.wr_clk(pclk),.wr_en(push&&!full&&!wr_busy),.din(camera_word),.full(full),.wr_rst_busy(wr_busy),
  .rd_clk(sys_clk),.rd_en(word_valid),.dout(stream),.empty(empty),.rd_rst_busy(rd_busy),
  .sleep(1'b0),.injectdbiterr(1'b0),.injectsbiterr(1'b0));
 wire [8:0] roi_x,cx,left_x,center_x,right_x;
 wire [7:0] roi_y,roi_w,roi_h,threshold,contrast;wire [15:0] dark_count,event_seq;
 wire [1:0] calibrate,cal_active,direction,event_direction;wire [2:0] calibrated;
 wire clear,config_changed,sample,feature_valid,valid,stale,cal_error,commit;
 wire snapshot_request,snapshot_release,snapshot_ready,snapshot_busy;
 wire [16:0] snapshot_addr,display_addr;wire [7:0] snapshot_data,display_data;
 eye_features features_i(sys_clk,rst,config_changed,word_valid,stream,roi_x,roi_y,roi_w,roi_h,threshold,
  sample,feature_valid,cx,dark_count,contrast);
 gaze_control gaze_i(sys_clk,rst,clear||config_changed,sample,feature_valid&&!snapshot_busy&&ready,cx,
  calibrate,direction,valid,calibrated,cal_active,cal_error,left_x,center_x,right_x,commit,event_direction,event_seq,stale);
 serial_control serial_i(sys_clk,rst,uart_rx,uart_tx,direction,cal_active,event_direction,valid,feature_valid,stale,ready,fault,cal_error,
  calibrated,cx,dark_count,event_seq,chip_id,contrast,calibrate,clear,config_changed,roi_x,roi_y,roi_w,roi_h,threshold,
  snapshot_request,snapshot_ready,snapshot_release,snapshot_addr,snapshot_data);
 wire pix_clk,pix_clk5,locked,pix_rst;
 display_clocks #(.MULT_MASTER(63.0),.DIV_MASTER(5),.DIV_5X(5.0),.DIV_1X(25),.IN_PERIOD(20.0))
  clocks_i(sys_clk,rst,pix_clk,pix_clk5,locked);
 // LOCKED deasserts on MMCM reset; avoid a combinational reset-OR before CDC.
 reset_sync display_reset(pix_clk,!locked,pix_rst);
 frame_store frames_i(sys_clk,rst,word_valid,stream,snapshot_request,snapshot_release,snapshot_ready,snapshot_busy,
  snapshot_addr,snapshot_data,pix_clk,display_addr,display_data);
 wire [45:0] display_control;
 visual_mailbox #(.WIDTH(46)) visual_i(sys_clk,rst,{roi_x,cx,roi_y,roi_w,roi_h,direction,valid,ready},pix_clk,pix_rst,display_control);
 eye_display display_i(pix_clk,pix_clk5,pix_rst,display_data,display_control[45:37],display_control[36:28],
  display_control[27:20],display_control[19:12],display_control[11:4],display_control[3:2],display_control[1],display_control[0],
  display_addr,hdmi_data_p,hdmi_data_n,hdmi_clk_p,hdmi_clk_n);
 assign led={~valid,~ready};
endmodule
