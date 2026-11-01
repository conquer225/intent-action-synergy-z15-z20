`timescale 1ns/1ps
// Word [29]=frame end, [28]=frame good, [27:18]=x, [17:9]=y, [7:0]=green luma.
// Marker follows all pixels. Malformed lines, overflow and incomplete frames fail closed.
module screen_capture #(parameter WARM_FRAMES=10)(input wire pclk,rst,enable,vsync,href,input wire [7:0] data,
 input wire full,output reg push,output reg [29:0] word);
 reg vs_d,hr_d,half,seen,bad; reg [7:0] first;
 reg [10:0] x;reg [9:0] y;reg [3:0] warm;
 always @(posedge pclk)begin
  push<=0;vs_d<=vsync;hr_d<=href;
  if(rst||!enable)begin vs_d<=0;hr_d<=0;half<=0;seen<=0;bad<=0;x<=0;y<=0;warm<=0;word<=0;end
  else begin
   if(full)bad<=1;
   if(vsync&&!vs_d)begin
    if(!full)begin push<=1;word<={1'b1,(seen&&!bad&&y==480&&warm==WARM_FRAMES),28'b0};end
    seen<=1;bad<=0;x<=0;y<=0;half<=0;if(warm<WARM_FRAMES)warm<=warm+1'b1;
   end else if(!vsync&&seen)begin
    if(href)begin
     half<=!half;
     if(!half)first<=data;
     else begin
      if(x<640 && y<480 && !full)begin
       word<={2'b00,x[9:0],y[8:0],1'b0,first[2:0],data[7:5],first[2:1]};push<=1;
      end else bad<=1;
      if(x<2047)x<=x+1'b1;
     end
    end else if(hr_d)begin
     if(x!=640||half)bad<=1;
     x<=0;half<=0;if(y<1023)y<=y+1'b1;
    end
   end
  end
 end
endmodule
