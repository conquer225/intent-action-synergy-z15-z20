`timescale 1ns/1ps
module tb_capture;
 reg clk=0;always #10 clk=~clk;
 reg rst=1,vs=0,hr=0,full=0;reg [7:0] data=0;
 wire push;wire [27:0] word;
 camera_capture cap(clk,rst,1'b1,vs,hr,data,full,push,word);
 integer pixels=0,good=0,bad=0;
 always @(posedge clk)if(!rst&&push)begin
  if(word[27])begin
   if(word[26])begin if(pixels!=76800)$fatal(1,"good frame size %d",pixels);good=good+1;end else bad=bad+1;
   pixels=0;
  end else begin
   if(word[7:0]!=255)$fatal(1,"RGB565 green conversion");
   if(word[25:17]!==pixels%320 || word[16:9]!==pixels/320)$fatal(1,"pixel coordinates");
   pixels=pixels+1;
  end
 end
 task tick;begin @(negedge clk);end endtask
 task boundary;begin vs=1;repeat(8)tick();vs=0;repeat(8)tick();end endtask
 task frame(input bit short_line);
  begin
   for(integer y=0;y<240;y=y+1)begin
    hr=1;
    for(integer x=0;x<320;x=x+1)begin
     data=8'h07;tick();data=8'he0;tick();
    end
    // Extra odd byte makes line malformed but does not emit extra pixel.
    if(short_line&&y==200)begin data=0;tick();end
    hr=0;repeat(8)tick();
   end
  end
 endtask
 initial begin
  repeat(5)tick();rst=0;
  boundary();repeat(12)begin frame(0);boundary();end
  if(good!=3)$fatal(1,"warmup/good markers %d",good);
  frame(1);boundary();if(good!=3)$fatal(1,"malformed frame accepted");
  // FIFO full during blanking marks entire frame invalid.
  full=1;tick();full=0;frame(0);boundary();if(good!=3)$fatal(1,"overflow accepted");
  $display("PASS tb_capture: RGB565, 320x240, startup, malformed line, FIFO overflow");$finish;
 end
 initial begin #100000000;$fatal(1,"capture timeout");end
endmodule
