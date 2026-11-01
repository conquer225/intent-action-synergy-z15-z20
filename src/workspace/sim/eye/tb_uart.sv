`timescale 1ns/1ps
module tb_uart;
 reg clk=0;always #10 clk=~clk;
 reg rst=1,start=0;reg [7:0] din=0;wire tx,busy,rv;wire [7:0] dout;
 uart #(.CLKS_PER_BIT(16)) u(clk,rst,tx,dout,rv,din,start,busy,tx);
 integer i;
 initial begin
  repeat(5)@(negedge clk);rst=0;
  for(i=0;i<256;i=i+1)begin
   @(negedge clk);din=i;start=1;@(negedge clk);start=0;
   wait(rv);if(dout!==din)$fatal(1,"UART mismatch %x %x",din,dout);
   wait(!busy);repeat(4)@(negedge clk);
  end
  $display("PASS tb_uart: all 256 byte values 8N1");$finish;
 end
 initial begin #2000000;$fatal(1,"UART timeout");end
endmodule
