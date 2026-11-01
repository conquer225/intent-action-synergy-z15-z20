`timescale 1ns/1ps
// Text keys l/c/r: calibrate; x: clear; p: snapshot. Binary ROI packet documented in docs/eye_control.md.
module serial_control #(parameter REPORT_CYCLES=5000000,UART_DIV=434)(
 input wire clk,rst,rx,output wire tx,
 input wire [1:0] direction,cal_active,event_direction,input wire valid,feature_valid,stale,ready,fault,cal_error,
 input wire [2:0] calibrated,input wire [8:0] cx,input wire [15:0] dark_count,event_seq,chip_id,
 input wire [7:0] contrast,
 output reg [1:0] calibrate,output reg clear,config_changed,
 output reg [8:0] roi_x,output reg [7:0] roi_y,roi_w,roi_h,threshold,
 output reg snapshot_request,input wire snapshot_ready,
 output reg snapshot_release,output reg [16:0] snapshot_addr,input wire [7:0] snapshot_data);
 wire [7:0] rx_byte;wire rx_valid,tx_busy;reg tx_start;reg [7:0] tx_byte;
 uart #(.CLKS_PER_BIT(UART_DIV)) uart_i(clk,rst,rx,rx_byte,rx_valid,tx_byte,tx_start,tx_busy,tx);
 reg [3:0] parse;reg [7:0] payload[0:5];reg [7:0] checksum;
 reg [23:0] rx_timeout,report_timer;
 reg [2:0] sending;reg [6:0] char_count;
 reg [8*64-1:0] line_data;
 reg [16:0] image_count;
 function automatic [7:0] hex(input [3:0] n);hex=n<10?8'h30+n:8'h41+n-10;endfunction
 function automatic [7:0] dc(input [1:0] n);case(n)1:dc="L";2:dc="C";3:dc="R";default:dc="I";endcase endfunction
 wire [8*64-1:0] status_line={"EYE ",dc(direction)," V",(valid?8'h31:8'h30)," F",(feature_valid?8'h31:8'h30),
 " C",hex({1'b0,calibrated})," A",hex({2'b0,cal_active})," X",hex({3'b0,cx[8]}),hex(cx[7:4]),hex(cx[3:0]),
 " N",hex(dark_count[15:12]),hex(dark_count[11:8]),hex(dark_count[7:4]),hex(dark_count[3:0]),
 " Q",hex(contrast[7:4]),hex(contrast[3:0])," E",hex(event_seq[15:12]),hex(event_seq[11:8]),hex(event_seq[7:4]),hex(event_seq[3:0]),
 " D",dc(event_direction)," S",(stale?8'h31:8'h30)," I",hex(chip_id[15:12]),hex(chip_id[11:8]),hex(chip_id[7:4]),hex(chip_id[3:0]),
 " R",(ready?8'h31:8'h30)," !",(fault?8'h31:8'h30)," K",(cal_error?8'h31:8'h30),8'h0d,8'h0a,24'b0};
 always @(posedge clk)begin
  calibrate<=0;clear<=0;config_changed<=0;snapshot_request<=0;snapshot_release<=0;tx_start<=0;
  if(rst)begin
   roi_x<=120;roi_y<=96;roi_w<=80;roi_h<=40;threshold<=64;
   parse<=0;checksum<=0;rx_timeout<=0;report_timer<=0;sending<=0;char_count<=0;line_data<=0;image_count<=0;snapshot_addr<=0;tx_byte<=0;
  end else begin
   if(report_timer<REPORT_CYCLES)report_timer<=report_timer+1'b1;
   if(parse!=0)begin if(rx_timeout==5000000)parse<=0;else rx_timeout<=rx_timeout+1'b1;end
   if(rx_valid)begin
    rx_timeout<=0;
    if(parse==0)case(rx_byte)
     "l":calibrate<=1;"c":calibrate<=2;"r":calibrate<=3;"x":clear<=1;"p":snapshot_request<=1;
     8'ha5:begin parse<=1;checksum<=0;end
    endcase
    else if(parse<=6)begin payload[parse-1]<=rx_byte;checksum<=checksum^rx_byte;parse<=parse+1'b1;end
    else if(parse==7)begin if(rx_byte==checksum)parse<=8;else parse<=0;end
    else begin
     parse<=0;
     if(rx_byte==8'h5a && payload[0]<=1 && payload[3]>=16 && payload[4]>=8 &&
       {payload[0],payload[1]}+{8'b0,payload[3]}<=320 && {1'b0,payload[2]}+{1'b0,payload[4]}<=240 && payload[5]>0)begin
      roi_x<={payload[0][0],payload[1]};roi_y<=payload[2];roi_w<=payload[3];roi_h<=payload[4];threshold<=payload[5];config_changed<=1;
     end
    end
   end
   if(!tx_busy&&!tx_start)case(sending)
    0: if(snapshot_ready)begin
        // Eight-byte binary header: ZIMG, little-endian width=320, height=240.
        line_data<={"ZIMG",8'h40,8'h01,8'hf0,8'h00,448'b0};char_count<=8;sending<=2;snapshot_addr<=0;image_count<=0;
       end else if(report_timer==REPORT_CYCLES)begin line_data<=status_line;char_count<=61;sending<=1;report_timer<=0;end
    1,2: begin
      tx_byte<=line_data[511:504];tx_start<=1;line_data<={line_data[503:0],8'b0};char_count<=char_count-1'b1;
      if(char_count==1)begin if(sending==1)sending<=0;else sending<=3;end
     end
    3: begin
      tx_byte<=snapshot_data;tx_start<=1;
      if(image_count==76799)begin sending<=4;end
      else begin image_count<=image_count+1'b1;snapshot_addr<=snapshot_addr+1'b1;end
     end
    4: begin snapshot_release<=1;sending<=5;end
    5: if(!snapshot_ready)sending<=0;
    default:sending<=0;
   endcase
  end
 end
endmodule
