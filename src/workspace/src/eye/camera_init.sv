`timescale 1ns/1ps
module camera_init #(parameter WAIT_CYCLES=1000000, SCCB_DIV=125)(
 input wire clk,rst, output wire scl,inout wire sda,
 output reg cam_reset_n,output wire cam_pwdn,
 output reg ready,fault,output reg [15:0] chip_id);
 assign cam_pwdn=0;
 reg [23:0] delay_count,request;
 reg [7:0] index;
 wire [23:0] rom;
 reg [3:0] state;reg start,rd;
 wire busy,done,error; wire [7:0] value;
 camera_rom rom_i(index,rom);
 sccb_master #(.DIV(SCCB_DIV)) bus_i(clk,rst,start,rd,request,busy,done,error,value,scl,sda);
 always @(posedge clk) begin
  start<=0;
  if(rst)begin state<=0;delay_count<=0;cam_reset_n<=0;ready<=0;fault<=0;index<=0;chip_id<=0;rd<=0;request<=0;end
  else case(state)
   0: if(delay_count==WAIT_CYCLES-1)begin delay_count<=0;cam_reset_n<=1;state<=1;end else delay_count<=delay_count+1'b1;
   1: if(delay_count==WAIT_CYCLES-1)begin delay_count<=0;request<=24'h300a00;rd<=1;start<=1;state<=2;end else delay_count<=delay_count+1'b1;
   2: if(done)begin
       if(error)begin fault<=1;state<=9;end
       else begin chip_id[15:8]<=value;request<=24'h300b00;start<=1;state<=3;end
      end
   3: if(done)begin chip_id[7:0]<=value;
       if(error || chip_id[15:8]!=8'h56 || value!=8'h40)begin fault<=1;state<=9;end
       else begin rd<=0;state<=4;end
      end
   4: begin request<=rom;start<=1;state<=5;end
   5: if(done)begin
       if(error)begin fault<=1;state<=9;end
       else if(index==247)begin ready<=1;state<=8;end
       else begin index<=index+1'b1;delay_count<=0;state<=6;end
      end
   // Conservative 20ms after every write (about 5 sec startup).
   6: if(delay_count==WAIT_CYCLES-1)state<=4;else delay_count<=delay_count+1'b1;
   8: ;
   9: if(delay_count==WAIT_CYCLES*4-1)begin state<=0;delay_count<=0;index<=0;cam_reset_n<=0;fault<=0;end else delay_count<=delay_count+1'b1;
   default:state<=0;
  endcase
 end
endmodule
