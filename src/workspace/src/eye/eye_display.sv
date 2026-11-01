`timescale 1ns/1ps
// 640x480 @60 Hz, 25.2 MHz. Preview doubled from 320x240; overlay is diagnostic only.
module eye_display(input wire clk,clk5,rst,input wire [7:0] gray,
 input wire [8:0] roi_x,cx,input wire [7:0] roi_y,roi_w,roi_h,
 input wire [1:0] direction,input wire valid,ready,
 output wire [16:0] addr,output wire [2:0] data_p,data_n,output wire clock_p,clock_n);
 reg [9:0] x,y;reg [9:0] xd,yd;reg de,hs,vs;reg [23:0] rgb;
 wire active=x<640&&y<480;
 assign addr=active?(y[9:1]*17'd320+x[9:1]):17'd0;
 always @(posedge clk)begin
  if(rst)begin x<=0;y<=0;xd<=0;yd<=0;de<=0;hs<=1;vs<=1;end
  else begin
   if(x==799)begin x<=0;if(y==524)y<=0;else y<=y+1'b1;end else x<=x+1'b1;
   xd<=x;yd<=y;de<=active;hs<=!(x>=656&&x<752);vs<=!(y>=490&&y<492);
  end
 end
 always @* begin
  rgb=ready?{gray,gray,gray}:24'h202040;
  if((xd[9:1]==roi_x||xd[9:1]==roi_x+roi_w-1)&&yd[9:1]>=roi_y&&yd[9:1]<roi_y+roi_h ||
     (yd[9:1]==roi_y||yd[9:1]==roi_y+roi_h-1)&&xd[9:1]>=roi_x&&xd[9:1]<roi_x+roi_w)rgb=24'h00ffff;
  if(valid && xd[9:1]==cx && yd[9:1]>=roi_y && yd[9:1]<roi_y+roi_h)rgb=24'hff0000;
  if(yd<12)begin
   if(!valid)rgb=24'h802000;
   else if(direction==1&&xd<213||direction==2&&xd>=213&&xd<426||direction==3&&xd>=426)rgb=24'h00ff00;
   else rgb=24'h002000;
  end
 end
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
