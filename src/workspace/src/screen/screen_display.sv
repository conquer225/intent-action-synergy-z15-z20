`timescale 1ns/1ps
module screen_display(input wire clk,clk5,rst,input wire [7:0] gray,
 input wire [127:0] control,output wire [16:0] addr,
 output wire [2:0] data_p,data_n,output wire clock_p,clock_n);
 wire [23:0] rgb;wire de,hs,vs;wire [9:0] xd,yd;
 screen_pixels pixels_i(clk,rst,gray,control[127:77],control[76:26],control[25:23],
  control[22:21],control[20:19],control[18:17],control[16],control[15],control[14],control[13],
  control[12:8],control[7:4],control[3:0],addr,rgb,de,hs,vs,xd,yd);
 wire [2:0] serial;wire serial_clk;
 dvi_generator dvi_i(.i_pix_clk(clk),.i_pix_clk_5x(clk5),.i_rst(rst),.i_de(de),
  .i_data_ch0(rgb[7:0]),.i_data_ch1(rgb[15:8]),.i_data_ch2(rgb[23:16]),
  .i_ctrl_ch0({vs,hs}),.i_ctrl_ch1(2'b0),.i_ctrl_ch2(2'b0),
  .o_tmds_ch0_serial(serial[0]),.o_tmds_ch1_serial(serial[1]),.o_tmds_ch2_serial(serial[2]),.o_tmds_chc_serial(serial_clk));
 genvar i;generate for(i=0;i<3;i=i+1)begin:outputs
  OBUFDS #(.IOSTANDARD("TMDS_33")) ob(.I(serial[i]),.O(data_p[i]),.OB(data_n[i]));
 end endgenerate
 OBUFDS #(.IOSTANDARD("TMDS_33")) cb(.I(serial_clk),.O(clock_p),.OB(clock_n));
endmodule
