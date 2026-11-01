`timescale 1ns/1ps
// Word [27]=frame end, [26]=frame good, [25:17]=x, [16:9]=y, [7:0]=green luma.
// Marker follows all pixels. Malformed lines, overflow and incomplete frames fail closed.
module camera_capture(input wire pclk,rst,enable,vsync,href,input wire [7:0] data,
 input wire full,output reg push,output reg [27:0] word);
 reg vs_d,hr_d,half,seen,bad; reg [7:0] first;
 reg [9:0] x;reg [8:0] y;reg [3:0] warm;
 always @(posedge pclk)begin
  push<=0;vs_d<=vsync;hr_d<=href;
  if(rst||!enable)begin vs_d<=0;hr_d<=0;half<=0;seen<=0;bad<=0;x<=0;y<=0;warm<=0;word<=0;end
  else begin
   if(full)bad<=1;
   if(vsync&&!vs_d)begin
    if(!full)begin push<=1;word<={1'b1,(seen&&!bad&&y==240&&warm==10),26'b0};end
    seen<=1;bad<=0;x<=0;y<=0;half<=0;if(warm<10)warm<=warm+1'b1;
   end else if(!vsync&&seen)begin
    if(href)begin
     half<=!half;
     if(!half)first<=data;
     else begin
      if(x<320 && y<240 && !full)begin
       word<={2'b00,x[8:0],y[7:0],1'b0,first[2:0],data[7:5],first[2:1]};push<=1;
      end else bad<=1;
      if(x<1023)x<=x+1'b1;
     end
    end else if(hr_d)begin
     if(x!=320||half)bad<=1;
     x<=0;half<=0;if(y<511)y<=y+1'b1;
    end
   end
  end
 end
endmodule
