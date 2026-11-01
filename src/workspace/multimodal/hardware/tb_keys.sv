`timescale 1ns/1ps
module tb_keys;
reg clk=0,rst=0;reg [1:0] keys=0;wire [1:0] value;
always #5 clk=~clk;
key_inputs dut(.aclk(clk),.aresetn(rst),.keys(keys),.value(value));
initial begin
 #20;if(value!=3)$fatal(1,"reset state released");rst=1;
 @(negedge clk);keys=2;@(negedge clk);@(negedge clk);
 if(value!=2)$fatal(1,"both keys pass through two-stage synchronization");
 keys=1;@(negedge clk);@(negedge clk);
 if(value!=1)$fatal(1,"second key independent");
 $display("PL keys synchronizer/reset/independent input PASS");$finish;
end
initial begin #1000;$fatal(1,"timeout");end
endmodule
