`timescale 1ns/1ps
module eye_features(input wire clk,rst,config_changed,
 input wire word_valid,input wire [27:0] word,
 input wire [8:0] roi_x,input wire [7:0] roi_y,roi_w,roi_h,threshold,
 output reg sample,valid,output reg [8:0] cx,output reg [15:0] dark_count,
 output reg [7:0] contrast);
 wire pixel=word_valid&&!word[27];wire frame=word_valid&&word[27];
 wire [8:0] x=word[25:17];wire [7:0] y=word[16:9],gray=word[7:0];
 wire in_roi=(x>=roi_x && {1'b0,x}<({1'b0,roi_x}+roi_w) && y>=roi_y && {1'b0,y}<({1'b0,roi_y}+roi_h));
 wire [15:0] area=roi_w*roi_h;
 reg [23:0] sum_x;reg [15:0] count,border;reg [16:0] pixels;
 reg [7:0] lo,hi;reg skip;
 reg [8:0] xmin,xmax;reg [7:0] ymin,ymax;
 wire [9:0] box_w={1'b0,xmax}-{1'b0,xmin}+1'b1;
 wire [8:0] box_h={1'b0,ymax}-{1'b0,ymin}+1'b1;
 reg [23:0] quotient;reg [16:0] remainder;reg [15:0] divisor;
 reg [4:0] bits_left;
 wire [17:0] shifted={remainder,quotient[23]};
 wire subtract=shifted>={2'b0,divisor};
 wire [23:0] next_q={quotient[22:0],subtract};
 always @(posedge clk)begin
  sample<=0;
  if(rst||config_changed)begin sum_x<=0;count<=0;border<=0;pixels<=0;lo<=255;hi<=0;skip<=1;bits_left<=0;valid<=0;cx<=0;dark_count<=0;contrast<=0;quotient<=0;remainder<=0;divisor<=1;xmin<=511;xmax<=0;ymin<=255;ymax<=0;end
  else begin
   if(pixel)begin
    if(pixels<131071)pixels<=pixels+1'b1;
    if(in_roi)begin
     if(gray<lo)lo<=gray;if(gray>hi)hi<=gray;
     if(gray<threshold)begin
      count<=count+1'b1;sum_x<=sum_x+x;
      if(x<xmin)xmin<=x;if(x>xmax)xmax<=x;
      if(y<ymin)ymin<=y;if(y>ymax)ymax<=y;
      if(x==roi_x || x==roi_x+roi_w-1 || y==roi_y || y==roi_y+roi_h-1)border<=border+1'b1;
     end
    end
   end
   if(frame)begin
    dark_count<=count;contrast<=hi-lo;
    if(!skip && word[26] && pixels==76800 && count>=16 && count>=(area>>7) && count<(area>>1) && hi>=lo+9'd30 && border<(count>>2) &&
       box_h>=3 && box_w<=(({2'b0,roi_w}*3)>>2) && box_h<=(({2'b0,roi_h}*3)>>2) && box_w<=box_h*4 && box_h<=box_w*2 && bits_left==0)begin
     quotient<=sum_x;remainder<=0;divisor<=count;bits_left<=24;
    end else begin sample<=1;valid<=0;end
    sum_x<=0;count<=0;border<=0;pixels<=0;lo<=255;hi<=0;skip<=0;xmin<=511;xmax<=0;ymin<=255;ymax<=0;
   end
   if(bits_left!=0)begin
    quotient<=next_q;remainder<=subtract?shifted-divisor:shifted;bits_left<=bits_left-1'b1;
    if(bits_left==1)begin cx<=next_q[8:0];valid<=1;sample<=1;end
   end
  end
 end
endmodule

