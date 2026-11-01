`timescale 1ns/1ps
module tb_video_epoch;
 reg clk=0; always #5 clk=~clk;
 reg reset_n=0,awvalid=0,awready=1,bvalid=0,bready=1;
 reg [31:0] awaddr=0;reg [7:0] awlen=1;reg [2:0] awsize=3;reg [1:0] bresp=0;
 wire [1:0] writer_index,completed_index;wire [31:0] write_epoch,completed_sequence;
 wire writer_valid,completed_valid,fault,event_changed;
 z20_video_epoch #(.BASE(32'h1000),.STRIDE(64),.HEIGHT(2),.ACTIVE(16)) dut(.*);
 task aw(input [31:0] address);
  @(negedge clk); awaddr=address;awvalid=1;@(negedge clk);awvalid=0;@(negedge clk);
 endtask
 task response;
  @(negedge clk);bvalid=1;@(negedge clk);bvalid=0;@(negedge clk);
 endtask
 initial begin
  repeat(3) @(negedge clk);reset_n=1;
  aw('h1000); if(write_epoch!=1 || writer_index!=0 || completed_valid) $fatal(1,"first write");
  response(); if(completed_valid) $fatal(1,"partial frame reported complete");
  aw('h1040); if(completed_valid) $fatal(1,"AW completion is not B completion");
  response(); if(!completed_valid || completed_index!=0 || completed_sequence!=1) $fatal(1,"completed frame0");
  aw('h1080); aw('h10c0);
  response(); if(completed_sequence!=1) $fatal(1,"outstanding final response");
  response(); if(completed_sequence!=2 || completed_index!=1 || write_epoch!=2) $fatal(1,"frame1");
  aw('h1100);response();aw('h1140);response();
  aw('h1000); if(write_epoch!=4 || writer_index!=0 || completed_sequence!=3) $fatal(1,"ring ABA generation");
  response(); aw('h1040);bresp=2;response();
  if(!fault || completed_valid) $fatal(1,"AXI error must invalidate analysis");
  // Software parking must not make a repeated slot invisible to generation.
  reset_n=0;repeat(2) @(negedge clk);reset_n=1;bresp=0;
  aw('h1000);response();aw('h1040);response();
  aw('h1000);
  if(write_epoch!=2 || completed_sequence!=1) $fatal(1,"same-slot frame restart generation");
  reset_n=0;repeat(2) @(negedge clk);reset_n=1;
  awlen=0;aw('h1000);response();awlen=1;aw('h1040);response();
  if(!fault || completed_valid) $fatal(1,"missing pixels must not form a complete frame");
  reset_n=0;repeat(2) @(negedge clk);reset_n=1;
  @(negedge clk);awaddr='h1000;awvalid=1;
  @(negedge clk);awaddr='h1040;
  @(negedge clk);awvalid=0;
  @(negedge clk);bvalid=1;
  repeat(2) @(negedge clk);bvalid=0;
  repeat(2) @(negedge clk);
  if(fault || completed_sequence!=1) $fatal(1,"consecutive pipelined bursts/responses");
  repeat(3) @(negedge clk);
  $display("PASS: frame generation, B response fence, ring wrap and AXI fault");$finish;
 end
 initial begin #10000;$fatal(1,"timeout");end
endmodule
