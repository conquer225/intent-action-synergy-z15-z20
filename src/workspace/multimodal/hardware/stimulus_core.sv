`timescale 1ns/1ps
module stimulus_core #(parameter WIDTH=1280,HEIGHT=720)(
 input wire clk,resetn,frame_start,de,input wire [15:0] x,y,input wire [23:0] in_data,
 input wire apply,enable,input wire [31:0] epoch,output reg [23:0] pixel,
 output reg [31:0] frames,applied_epoch,output wire active,
 output reg [31:0] ticks,max_gap,output wire [127:0] rising_counts
);
 reg enabled;reg [7:0] age;reg [5:0] phase[0:3];integer i;
 reg [31:0] rising[0:3],gap;reg frame_seen;
 genvar g;generate for(g=0;g<4;g=g+1)begin:count_out
  assign rising_counts[g*32+:32]=rising[g];
 end endgenerate
 assign active=enabled && age<120;
 always @(posedge clk)begin
  if(!resetn)begin enabled<=0;age<=255;frames<=0;applied_epoch<=0;ticks<=0;max_gap<=0;gap<=0;frame_seen<=0;
   for(i=0;i<4;i=i+1)begin phase[i]<=0;rising[i]<=0;end
  end
  else begin
   ticks<=ticks+1; if(gap!=32'hffffffff)gap<=gap+1;
   if(frame_start)begin
    gap<=0;frame_seen<=1;
    if(frame_seen && gap+1>max_gap)max_gap<=gap+1;
    frames<=frames+1;
    if(age<255)age<=age+1;
    for(i=0;i<4;i=i+1)begin
     phase[i]<=phase[i]+8+2*i>=60?phase[i]+8+2*i-60:phase[i]+8+2*i;
     if(active && phase[i]+8+2*i>=60)rising[i]<=rising[i]+1;
    end
   end
   if(apply)begin
    enabled<=enable;age<=0;
    if(epoch!=applied_epoch || !enabled)begin
     applied_epoch<=epoch;frames<=0;max_gap<=0;gap<=0;frame_seen<=0;
     for(i=0;i<4;i=i+1)begin phase[i]<=0;rising[i]<=0;end
    end
   end
  end
 end
 integer region;
 always @*begin
  pixel=in_data;region=0;
  if(de && active && y>=HEIGHT/3 && y<HEIGHT*3/4)begin
   if(x>=WIDTH/4)region=1;
   if(x>=WIDTH/2)region=2;
   if(x>=WIDTH*3/4)region=3;
   if(x%(WIDTH/4)>=WIDTH/32 && x%(WIDTH/4)<WIDTH/4-WIDTH/32)
    pixel=phase[region]<30?24'hffffff:24'h101010;
  end
 end
endmodule
