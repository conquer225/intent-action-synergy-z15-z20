`timescale 1ns/1ps
// Pure pixel renderer, independently simulated and reused by the HDMI wrapper.
module screen_pixels(input wire clk,rst,input wire [7:0] gray,
 input wire [50:0] roi0,roi1,input wire [2:0] mode,
 input wire [1:0] direction,eye_valid,event_direction,
 input wire valid,ready,settled,armed,input wire [4:0] cal_count,
 input wire [3:0] reason,progress,
 output wire [16:0] addr,output reg [23:0] rgb,output reg de,hs,vs,
 output reg [9:0] xd,yd);
 reg [9:0] x,y;
 wire active=x<640&&y<480;
 assign addr=active?y[9:1]*17'd320+x[9:1]:17'd0;
 always @(posedge clk)begin
  if(rst)begin x<=0;y<=0;xd<=0;yd<=0;de<=0;hs<=1;vs<=1;end
  else begin
   if(x==799)begin x<=0;if(y==524)y<=0;else y<=y+1'b1;end else x<=x+1'b1;
   xd<=x;yd<=y;de<=active;hs<=!(x>=656&&x<752);vs<=!(y>=490&&y<492);
  end
 end
 function automatic [34:0] glyph(input [7:0] ch);
  case(ch)
   "A":glyph=35'b01110_10001_10001_11111_10001_10001_10001;
   "B":glyph=35'b11110_10001_10001_11110_10001_10001_11110;
   "C":glyph=35'b01111_10000_10000_10000_10000_10000_01111;
   "D":glyph=35'b11110_10001_10001_10001_10001_10001_11110;
   "E":glyph=35'b11111_10000_10000_11110_10000_10000_11111;
   "F":glyph=35'b11111_10000_10000_11110_10000_10000_10000;
   "G":glyph=35'b01111_10000_10000_10111_10001_10001_01111;
   "H":glyph=35'b10001_10001_10001_11111_10001_10001_10001;
   "I":glyph=35'b11111_00100_00100_00100_00100_00100_11111;
   "J":glyph=35'b00111_00010_00010_00010_10010_10010_01100;
   "K":glyph=35'b10001_10010_10100_11000_10100_10010_10001;
   "L":glyph=35'b10000_10000_10000_10000_10000_10000_11111;
   "M":glyph=35'b10001_11011_10101_10101_10001_10001_10001;
   "N":glyph=35'b10001_11001_10101_10011_10001_10001_10001;
   "O":glyph=35'b01110_10001_10001_10001_10001_10001_01110;
   "P":glyph=35'b11110_10001_10001_11110_10000_10000_10000;
   "Q":glyph=35'b01110_10001_10001_10001_10101_10010_01101;
   "R":glyph=35'b11110_10001_10001_11110_10100_10010_10001;
   "S":glyph=35'b01111_10000_10000_01110_00001_00001_11110;
   "T":glyph=35'b11111_00100_00100_00100_00100_00100_00100;
   "U":glyph=35'b10001_10001_10001_10001_10001_10001_01110;
   "V":glyph=35'b10001_10001_10001_10001_10001_01010_00100;
   "W":glyph=35'b10001_10001_10001_10101_10101_10101_01010;
   "X":glyph=35'b10001_10001_01010_00100_01010_10001_10001;
   "Y":glyph=35'b10001_10001_01010_00100_00100_00100_00100;
   "Z":glyph=35'b11111_00001_00010_00100_01000_10000_11111;
   "1":glyph=35'b00100_01100_00100_00100_00100_00100_01110;
   "2":glyph=35'b01110_10001_00001_00010_00100_01000_11111;
   "3":glyph=35'b11110_00001_00001_01110_00001_00001_11110;
   ":":glyph=35'b00000_00100_00100_00000_00100_00100_00000;
   default:glyph=0;
  endcase
 endfunction
 // Fixed 32-character strings, top-left aligned with zero padding on the right.
 function automatic text_on(input [255:0] text,input integer ox,oy,scale);
  integer col,row,n;reg [7:0] ch;reg [34:0] bits;
  begin
   text_on=0;
   if(xd>=ox&&yd>=oy&&xd<ox+32*6*scale&&yd<oy+7*scale)begin
    col=(xd-ox)/scale;row=(yd-oy)/scale;n=col/6;
    ch=text[255-n*8-:8];bits=glyph(ch);
    if(col%6<5)text_on=bits[34-row*5-col%6];
   end
  end
 endfunction
 function automatic border(input [50:0] box);
  reg [10:0] bx,by,bw,bh;
  begin
   bx={1'b0,box[50:41]};by={2'b0,box[40:32]};bw={3'b0,box[31:24]};bh={3'b0,box[23:16]};
   border=xd>=bx&&xd<bx+bw&&yd>=by&&yd<by+bh&&(xd<bx+2||xd>=bx+bw-2||yd<by+2||yd>=by+bh-2);
  end
 endfunction
 reg [1:0] tile;reg selected;reg [255:0] status_text,bottom_text;
 integer dot_x,bar_width;
 always @* begin
  tile=xd<216?1:xd<424?2:3;
  selected=mode>=1&&mode<=3?tile==mode:(mode==4&&valid&&tile==direction);
  dot_x=tile==1?108:tile==2?320:532;
  bar_width=mode==4?progress*35:cal_count*35;
  status_text={"KEEP YOUR HEAD STILL",96'b0};
  bottom_text={"LOOK AT THE WHITE DOT",88'b0};
  if(!ready)status_text={"WAITING FOR CAMERA",112'b0};
  else if(mode==0)status_text={"SETUP ON COMPUTER",120'b0};
  else if(mode==5)status_text={"CALIBRATION FAILED",112'b0};
  else if(mode>=1&&mode<=3)begin
   if(reason==2)status_text={"EYES NOT CLEAR",144'b0};
   else if(reason==3)status_text={"MOVE BACK TO POSITION",88'b0};
   else if(settled)status_text={"HOLD STILL: SAMPLING",96'b0};
   else status_text={"LOOK AT THE WHITE DOT",88'b0};
   bottom_text={"FOLLOW LEFT CENTER RIGHT",64'b0};
  end else begin
   if(valid)status_text={"TRACKING",192'b0};
   else if(reason==2)status_text={"EYES NOT CLEAR",144'b0};
   else if(reason==3)status_text={"MOVE BACK TO POSITION",88'b0};
   else if(reason==7)status_text={"SNAPSHOT: OUTPUT PAUSED",72'b0};
   else if(stale_condition(reason))status_text={"CAMERA FRAME LOST",120'b0};
   else status_text={"LOOK INSIDE A TARGET",96'b0};
   bottom_text=armed?{"HOLD TO CONFIRM",136'b0}:{"LOOK CENTER TO REARM",96'b0};
  end
  rgb=24'h101b2b;
  if(mode==0&&ready)begin
   rgb={gray,gray,gray};
   if(border(roi0))rgb=eye_valid[0]?24'h28e0a0:24'hffa640;
   if(border(roi1))rgb=eye_valid[1]?24'h28e0a0:24'hffa640;
   if(yd<64||yd>=424)rgb=24'h101b2b;
   if(text_on({"FRAME BOTH EYES ON PC",88'b0},32,442,2))rgb=24'hffffff;
  end else begin
   if(yd>=128&&yd<368&&((xd>=24&&xd<200)||(xd>=224&&xd<416)||(xd>=440&&xd<616)))begin
    rgb=selected?(mode==4?24'h12685f:24'h765619):24'h22334b;
    if((xd>=dot_x-10&&xd<dot_x+10&&yd>=210&&yd<230))rgb=selected?24'hffffff:24'h536174;
   end
   if(text_on({"LEFT",224'b0},60,284,4)||text_on({"CENTER",208'b0},248,284,4)||text_on({"RIGHT",216'b0},476,284,4))rgb=24'he6edf5;
   if(yd>=396&&yd<410&&xd>=40&&xd<600)rgb=xd<40+bar_width?24'h28d5ad:24'h29394a;
   if(text_on(bottom_text,32,438,2))rgb=24'hd4deeb;
  end
  if(text_on({"SCREEN GAZE",168'b0},32,24,2))rgb=24'hffffff;
  if(text_on(status_text,32,76,2))rgb=valid?24'h28d5ad:24'hffc26a;
  if(text_on(mode==0?{"SETUP",216'b0}:mode==4?{"RUN",232'b0}:{"CALIBRATE",184'b0},488,24,2))rgb=24'haebdd0;
 end
 function automatic stale_condition(input [3:0] code);stale_condition=code==9;endfunction
endmodule
