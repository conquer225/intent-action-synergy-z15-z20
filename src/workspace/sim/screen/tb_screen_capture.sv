`timescale 1ns/1ps
module tb_screen_capture;
 reg clk=0;always #10 clk=~clk;
 reg rst=1,vs=0,hr=0,full=0;reg [7:0] data=0;
 wire push;wire [29:0] word;
 screen_capture #(.WARM_FRAMES(2)) dut(clk,rst,1'b1,vs,hr,data,full,push,word);
 integer pixels=0,good=0;
 always @(posedge clk)if(!rst&&push)begin
  if(word[29])begin
   if(word[28])begin if(pixels!=307200)$fatal(1,"good frame size %d",pixels);good=good+1;end
   pixels=0;
  end else begin
   if(word[7:0]!=255)$fatal(1,"RGB565 green conversion");
   if(word[27:18]!==pixels%640 || word[17:9]!==pixels/640)$fatal(1,"VGA pixel coordinates");
   pixels=pixels+1;
  end
 end
 task tick;begin @(negedge clk);end endtask
 task boundary;begin vs=1;repeat(8)tick();vs=0;repeat(8)tick();end endtask
 task frame(input bit odd_byte,input integer lines);
  begin
   for(integer y=0;y<lines;y=y+1)begin
    hr=1;
    for(integer x=0;x<640;x=x+1)begin data=8'h07;tick();data=8'he0;tick();end
    if(odd_byte&&y==200)begin data=0;tick();end
    hr=0;repeat(8)tick();
   end
  end
 endtask
 initial begin
  repeat(5)tick();rst=0;boundary();
  frame(0,480);boundary();if(good!=0)$fatal(1,"warmup frame accepted");
  frame(0,480);boundary();if(good!=1)$fatal(1,"complete VGA rejected");
  frame(1,480);boundary();if(good!=1)$fatal(1,"odd byte accepted");
  frame(0,479);boundary();if(good!=1)$fatal(1,"missing line accepted");
  full=1;tick();full=0;frame(0,480);boundary();if(good!=1)$fatal(1,"FIFO overflow accepted");
  $display("PASS tb_screen_capture: VGA coordinates/RGB565, startup, odd-byte line, missing line, FIFO overflow");$finish;
 end
 initial begin #100000000;$fatal(1,"capture timeout");end
endmodule
