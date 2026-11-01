`timescale 1ns/1ps
// Exercise real frame RAM latency, binary framing and all image bytes over UART.
module tb_snapshot;
 reg clk=0;always #10 clk=~clk;
 reg rst=1,rx=1,wv=0;reg [27:0] word=0;
 wire tx,req,rel,ready,busy;wire [16:0] addr;wire [7:0] data;
 frame_store frames(clk,rst,wv,word,req,rel,ready,busy,addr,data,clk,17'b0,);
 serial_control #(.REPORT_CYCLES(16000000),.UART_DIV(8)) serial(
  clk,rst,rx,tx,2'b0,2'b0,2'b0,1'b0,1'b0,1'b0,1'b1,1'b0,1'b0,
  3'b0,9'b0,16'b0,16'b0,16'h5640,8'b0,,,,,,,,,req,ready,rel,addr,data);
 wire [7:0] observed;wire observed_valid;
 uart #(.CLKS_PER_BIT(8)) monitor(clk,rst,tx,observed,observed_valid,8'b0,1'b0,,);
 reg [63:0] header={"ZIMG",8'h40,8'h01,8'hf0,8'h00};
 integer count=0;reg [7:0] expected;
 always @(posedge clk)if(observed_valid)begin
  if(count<8)begin expected=header[63:56];header={header[55:0],8'b0};end
  else expected=(count-8)%251;
  if(observed!==expected)$fatal(1,"snapshot byte %0d: got %x expected %x",count,observed,expected);
  count=count+1;
 end
 task tick;begin @(negedge clk);end endtask
 task send(input [7:0] b);begin
  tick();rx=0;repeat(8)tick();
  for(integer n=0;n<8;n=n+1)begin rx=b[n];repeat(8)tick();end
  rx=1;repeat(10)tick();
 end endtask
 initial begin
  repeat(5)tick();rst=0;send("p");
  if(!busy)$fatal(1,"snapshot request lost");
  word={2'b11,26'b0};wv=1;tick();wv=0;tick();
  for(integer y=0;y<240;y=y+1)for(integer x=0;x<320;x=x+1)begin
   word={2'b00,x[8:0],y[7:0],1'b0,8'b0};word[7:0]=(y*320+x)%251;wv=1;tick();
  end
  word={2'b11,26'b0};tick();wv=0;
  wait(count==76808);wait(!busy);tick();
  if(ready)$fatal(1,"snapshot did not release");
  $display("PASS tb_snapshot: 76800 pixel bytes through frame RAM and UART, header, release");$finish;
 end
 initial begin #160000000;$fatal(1,"snapshot timeout");end
endmodule
