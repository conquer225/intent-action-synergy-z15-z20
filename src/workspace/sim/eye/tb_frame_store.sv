`timescale 1ns/1ps
module tb_frame_store;
 reg clk=0,pclk=0;always #10 clk=~clk;always #19.84 pclk=~pclk;
 reg rst=1,wv=0,req=0,rel=0;reg [27:0] word=0;reg [16:0] addr=0;
 wire ready,busy;wire [7:0] data,display;
 frame_store store(clk,rst,wv,word,req,rel,ready,busy,addr,data,pclk,17'b0,display);
 task tick;begin @(negedge clk);end endtask
 task marker(input bit good);begin tick();wv=1;word={1'b1,good,26'b0};tick();wv=0;end endtask
 task pixel(input integer x,input integer y,input integer value);begin tick();word={2'b00,x[8:0],y[7:0],1'b0,value[7:0]};wv=1;end endtask
 initial begin
  repeat(5)tick();rst=0;req=1;tick();req=0;marker(1);
  for(integer y=0;y<240;y=y+1)for(integer x=0;x<320;x=x+1)pixel(x,y,x+y);
  marker(1);if(!ready||!busy)$fatal(1,"snapshot not complete");
  // Incoming live video must not overwrite frozen snapshot.
  for(integer y=0;y<240;y=y+1)for(integer x=0;x<320;x=x+1)pixel(x,y,0);
  tick();wv=0;
  for(integer n=0;n<76800;n=n+1)begin
   addr=n;repeat(2)tick();if(data!==((n%320+n/320)&255))$fatal(1,"snapshot pixel %d",n);
  end
  rel=1;tick();rel=0;tick();if(ready||busy)$fatal(1,"snapshot release");
  $display("PASS tb_frame_store: full image addressing and coherent freeze under live writes");$finish;
 end
 initial begin #10000000;$fatal(1,"snapshot timeout");end
endmodule
