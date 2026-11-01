`timescale 1ns/1ps
module uart #(parameter CLKS_PER_BIT=434)(input wire clk,rst,rx,
 output reg [7:0] rx_data,output reg rx_valid,input wire [7:0] tx_data,
 input wire tx_start,output wire tx_busy,output wire tx);
 (* ASYNC_REG="TRUE" *) reg [1:0] rx_sync;
 reg [15:0] rt,tt;reg [3:0] rb,tb;reg [7:0] rx_shift;
 reg [9:0] tx_shift;reg receiving;
 assign tx=tx_shift[0];assign tx_busy=tb!=0;
 always @(posedge clk)begin
  rx_sync<={rx_sync[0],rx};rx_valid<=0;
  if(rst)begin rt<=0;tt<=0;rb<=0;tb<=0;receiving<=0;rx_data<=0;rx_shift<=0;tx_shift<=10'h3ff;rx_sync<=3;end
  else begin
   if(!receiving)begin if(!rx_sync[1])begin receiving<=1;rt<=CLKS_PER_BIT/2-1;rb<=0;end end
   else if(rt!=0)rt<=rt-1'b1;
   else begin
    rt<=CLKS_PER_BIT-1;
    if(rb==0)begin if(rx_sync[1])receiving<=0;else rb<=1;end
    else if(rb<=8)begin rx_shift[rb-1]<=rx_sync[1];rb<=rb+1'b1;end
    else begin receiving<=0;if(rx_sync[1])begin rx_data<=rx_shift;rx_valid<=1;end end
   end
   if(tb==0)begin if(tx_start)begin tx_shift<={1'b1,tx_data,1'b0};tb<=10;tt<=CLKS_PER_BIT-1;end end
   else if(tt!=0)tt<=tt-1'b1;
   else begin tx_shift<={1'b1,tx_shift[9:1]};tb<=tb-1'b1;tt<=CLKS_PER_BIT-1;end
  end
 end
endmodule
