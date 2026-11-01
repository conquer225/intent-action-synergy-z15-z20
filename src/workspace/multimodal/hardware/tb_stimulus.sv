`timescale 1ns/1ps
module tb_stimulus;
 reg clk=0,rst=0,vsync=0,de=0,apply=0,en=0;reg [31:0] epoch=0;
 always #5 clk=~clk;
 wire [23:0] pixel;wire [31:0] frames,applied;wire active;
 stimulus_core #(.WIDTH(120),.HEIGHT(60)) dut(.clk(clk),.resetn(rst),.frame_start(vsync),.de(de),.x(16'd10),.y(16'd30),
 .in_data(24'habcdef),.apply(apply),.enable(en),.epoch(epoch),.pixel(pixel),.frames(frames),.applied_epoch(applied),.active(active));
 task frame;begin @(negedge clk);vsync=1;@(negedge clk);vsync=0;end endtask
 integer n;
 initial begin
  #20;rst=1;@(negedge clk);apply=1;en=1;epoch=7;
  @(negedge clk);apply=0;de=1;
  if(!active || applied!=7)$fatal(1,"stimulus applies epoch");
  for(n=0;n<60;n=n+1)frame();
  if(frames!=60)$fatal(1,"actual display frame accounting");
  if(dut.rising[0]!=8 || dut.rising[1]!=10 || dut.rising[2]!=12 || dut.rising[3]!=14)
   $fatal(1,"frequency witness counts actual rising transitions");
  for(n=0;n<61;n=n+1)frame();
  if(active)$fatal(1,"page lease expiry must blank stimuli");
  @(negedge clk);apply=1;en=0;epoch=8;@(negedge clk);apply=0;
  if(pixel!=24'habcdef || active)$fatal(1,"leaving page restores pixels");
  $display("Stimulus actual frames, page epoch, expiry and passthrough PASS");$finish;
 end
 initial begin #20000;$fatal(1,"timeout");end
endmodule
