`timescale 1ns/1ps
module tb_relative;
 reg clk=0;always #10 clk=~clk;
 reg rst=1,wv=0;reg [29:0] word=0;
 wire sample,valid;wire [7:0] ratio,q;wire [9:0] rx;wire [8:0] ry;wire [15:0] count;
 relative_eye dut(clk,rst,1'b0,wv,word,10'd60,9'd80,8'd80,8'd40,8'd64,8'd150,sample,valid,ratio,rx,ry,count,q);
 task tick;begin @(negedge clk);end endtask
 task frame(input integer gaze,shift,kind);
  reg [7:0] g;
  begin
   for(integer y=0;y<480;y=y+1)for(integer x=0;x<640;x=x+1)begin
    g=100;
    if((x-100-shift)*(x-100-shift)*64+(y-100)*(y-100)*625<=40000)g=200;
    if((x-100-shift-gaze)*(x-100-shift-gaze)+(y-100)*(y-100)<=25)g=20;
    if(kind==1)g=0;
    if(kind==2)begin g=100;if(x>80&&x<120&&y==100)g=20;end
    tick();word={2'b00,x[9:0],y[8:0],1'b0,g};wv=1;
   end
   tick();word={2'b11,28'b0};tick();wv=0;wait(sample);tick();
   $display("feature gaze=%0d shift=%0d kind=%0d ratio=%0d valid=%b count=%d",gaze,shift,kind,ratio,valid,count);
  end
 endtask
 integer left_ratio,middle_ratio,right_ratio;
 initial begin
  repeat(5)tick();rst=0;wv=1;word={2'b11,28'b0};tick();wv=0;
  frame(-8,0,0);if(!valid)$fatal(1,"left feature");left_ratio=ratio;
  frame(0,0,0);if(!valid)$fatal(1,"middle feature");middle_ratio=ratio;
  frame(8,0,0);if(!valid)$fatal(1,"right feature");right_ratio=ratio;
  if(left_ratio+6>middle_ratio||middle_ratio+6>right_ratio)$fatal(1,"no gaze separation");
  frame(8,6,0);if(!valid||ratio<right_ratio-1||ratio>right_ratio+1||rx<104)$fatal(1,"translation changed relative gaze");
  frame(0,0,1);if(valid)$fatal(1,"occlusion accepted");
  frame(0,0,2);if(valid)$fatal(1,"eyelid line accepted");
  $display("PASS tb_relative: VGA relative gaze, image translation invariance, occlusion and eyelid rejection");$finish;
 end
 initial begin #60000000;$fatal(1,"relative timeout");end
endmodule
