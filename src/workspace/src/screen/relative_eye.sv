`timescale 1ns/1ps
// One configured eye region. Relative dark/bright centroids; no face landmark model.
module relative_eye(
 input wire clk,rst,clear,word_valid,input wire [29:0] word,
 input wire [9:0] roi_x,input wire [8:0] roi_y,
 input wire [7:0] roi_w,roi_h,dark_threshold,bright_threshold,
 output reg sample,valid,output reg [7:0] ratio,
 output reg [9:0] ref_x,output reg [8:0] ref_y,
 output reg [15:0] dark_count,output reg [7:0] contrast);
 wire [9:0] x=word[27:18];wire [8:0] y=word[17:9];wire [7:0] gray=word[7:0];
 wire frame=word_valid&&word[29];
 wire in_roi=x>=roi_x&&{1'b0,x}<{1'b0,roi_x}+roi_w&&y>=roi_y&&{1'b0,y}<{1'b0,roi_y}+roi_h;
 wire pixel=word_valid&&!word[29]&&in_roi;
 reg [15:0] nd,nb,edge_n;
 reg [23:0] sx_d,sx_b,sy_b;
 reg [9:0] dx0,dx1,bx0,bx1;reg [8:0] dy0,dy1,by0,by1;
 reg [7:0] lo,hi;reg [18:0] pixels;reg skip;
 wire [15:0] area=roi_w*roi_h;
 wire [10:0] dw={1'b0,dx1}-{1'b0,dx0}+1,bw={1'b0,bx1}-{1'b0,bx0}+1;
 wire [9:0] dh={1'b0,dy1}-{1'b0,dy0}+1,bh={1'b0,by1}-{1'b0,by0}+1;
 wire shape_ok=nd>=8&&nd>=(area>>8)&&nd<(area>>1)&&nb>=16&&nb>=(area>>5)&&nb<area-(area>>4)
  &&hi>=lo+9'd30&&edge_n<(nd>>2)&&dh>=2&&dw<=roi_w*3/4&&dh<=roi_h*3/4
  &&dw<=dh*3&&dh<=dw*2&&bw>=12&&bh>=3;
 // Iterative unsigned division shared by dark-x, bright-x/y, normalized offset.
 reg [31:0] quotient;reg [16:0] rem;reg [15:0] divisor;
 reg [5:0] bits_left;reg [2:0] phase;
 reg [23:0] saved_bx,saved_by;reg [15:0] saved_nb;
 reg [10:0] saved_bw;reg [31:0] dark_q,bright_q;reg negative;
 wire [17:0] shifted={rem,quotient[31]};wire subtract=shifted>={2'b0,divisor};
 wire [31:0] next_q={quotient[30:0],subtract};
 always @(posedge clk)begin
  sample<=0;
  if(rst||clear)begin
   nd<=0;nb<=0;edge_n<=0;sx_d<=0;sx_b<=0;sy_b<=0;lo<=255;hi<=0;pixels<=0;skip<=1;
   dx0<=1023;dx1<=0;dy0<=511;dy1<=0;bx0<=1023;bx1<=0;by0<=511;by1<=0;
   sample<=0;valid<=0;ratio<=128;ref_x<=0;ref_y<=0;dark_count<=0;contrast<=0;
   quotient<=0;rem<=0;divisor<=1;bits_left<=0;phase<=0;negative<=0;
   saved_bx<=0;saved_by<=0;saved_nb<=1;saved_bw<=1;dark_q<=0;bright_q<=0;
  end else begin
   if(word_valid&&!word[29]&&pixels<524287)pixels<=pixels+1'b1;
   if(pixel)begin
    if(gray<lo)lo<=gray;if(gray>hi)hi<=gray;
    if(gray<dark_threshold)begin
     nd<=nd+1'b1;sx_d<=sx_d+x;
     if(x<dx0)dx0<=x;if(x>dx1)dx1<=x;if(y<dy0)dy0<=y;if(y>dy1)dy1<=y;
     if(x==roi_x||x==roi_x+roi_w-1||y==roi_y||y==roi_y+roi_h-1)edge_n<=edge_n+1'b1;
    end
    if(gray>=bright_threshold)begin
     nb<=nb+1'b1;sx_b<=sx_b+x;sy_b<=sy_b+y;
     if(x<bx0)bx0<=x;if(x>bx1)bx1<=x;if(y<by0)by0<=y;if(y>by1)by1<=y;
    end
   end
   if(frame)begin
    dark_count<=nd;contrast<=hi-lo;
    if(!skip&&word[28]&&pixels==307200&&shape_ok&&bits_left==0)begin
     quotient<={sx_d,8'b0};divisor<=nd;rem<=0;bits_left<=32;phase<=0;
     saved_bx<=sx_b;saved_by<=sy_b;saved_nb<=nb;saved_bw<=bw;
    end else begin sample<=1;valid<=0;end
    skip<=0;nd<=0;nb<=0;edge_n<=0;sx_d<=0;sx_b<=0;sy_b<=0;lo<=255;hi<=0;pixels<=0;
    dx0<=1023;dx1<=0;dy0<=511;dy1<=0;bx0<=1023;bx1<=0;by0<=511;by1<=0;
   end
   if(bits_left!=0)begin
    quotient<=next_q;rem<=subtract?shifted-divisor:shifted;bits_left<=bits_left-1'b1;
    if(bits_left==1)begin
     rem<=0;
     case(phase)
      0:begin dark_q<=next_q;quotient<={saved_bx,8'b0};divisor<=saved_nb;bits_left<=32;phase<=1;end
      1:begin bright_q<=next_q;ref_x<=next_q[17:8];quotient<={8'b0,saved_by};divisor<=saved_nb;bits_left<=32;phase<=2;end
      2:begin
       ref_y<=next_q[8:0];negative<=dark_q<bright_q;
       quotient<=dark_q>=bright_q?dark_q-bright_q:bright_q-dark_q;
       divisor<={4'b0,saved_bw,1'b0};bits_left<=32;phase<=3;
      end
      3:begin
       ratio<=next_q>120?(negative?8'd8:8'd248):(negative?8'd128-next_q[7:0]:8'd128+next_q[7:0]);
       valid<=next_q<=100;sample<=1;
      end
      default:begin valid<=0;sample<=1;end
     endcase
    end
   end
  end
 end
endmodule
