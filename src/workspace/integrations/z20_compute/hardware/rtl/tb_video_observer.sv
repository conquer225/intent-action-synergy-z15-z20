`timescale 1ns/1ps
module tb_video_observer;
 reg aclk=0;always #5 aclk=~aclk;
 reg aresetn=0;
 reg [7:0] s_axi_awaddr=0,s_axi_araddr=0;
 reg s_axi_awvalid=0,s_axi_wvalid=0,s_axi_bready=1,s_axi_arvalid=0,s_axi_rready=0;
 reg [31:0] s_axi_wdata=0;reg [3:0] s_axi_wstrb=15;
 wire s_axi_awready,s_axi_wready,s_axi_bvalid,s_axi_arready,s_axi_rvalid;
 wire [1:0] s_axi_bresp,s_axi_rresp;wire [31:0] s_axi_rdata;
 reg [31:0] cam0_awaddr=0,cam1_awaddr=0;
 reg [7:0] cam0_awlen=1,cam1_awlen=1;
 reg [2:0] cam0_awsize=3,cam1_awsize=3;
 reg cam0_awvalid=0,cam1_awvalid=0,cam0_awready=1,cam1_awready=1;
 reg cam0_bvalid=0,cam1_bvalid=0,cam0_bready=1,cam1_bready=1;
 reg [1:0] cam0_bresp=0,cam1_bresp=0;
 z20_video_observer dut(.*);
 task read_word(input [7:0] address,input [31:0] expected);
  @(negedge aclk);s_axi_araddr=address;s_axi_arvalid=1;
  @(negedge aclk);s_axi_arvalid=0;
  if(!s_axi_rvalid || s_axi_rdata!==expected || s_axi_rresp!=0) $fatal(1,"read %h got %h",address,s_axi_rdata);
  repeat(4) begin @(negedge aclk);if(!s_axi_rvalid || s_axi_rdata!==expected) $fatal(1,"backpressure");end
  s_axi_rready=1;@(negedge aclk);s_axi_rready=0;
 endtask
 initial begin
  repeat(3) @(negedge aclk);aresetn=1;
  read_word(0,32'h5a325643);read_word(4,1);read_word('h40,32'h01000000);
  @(negedge aclk);cam0_awaddr='h01000000;cam0_awvalid=1;
  @(negedge aclk);cam0_awvalid=0;
  repeat(3) @(negedge aclk);
  read_word('h14,1);read_word('h18,0);read_word('h10,1);
  // Accept address and data independently; all writes return SLVERR.
  @(negedge aclk);s_axi_awvalid=1;@(negedge aclk);s_axi_awvalid=0;
  repeat(3) @(negedge aclk);
  if(s_axi_bvalid) $fatal(1,"write response before data");
  s_axi_wvalid=1;@(negedge aclk);s_axi_wvalid=0;
  @(negedge aclk);
  if(!s_axi_bvalid || s_axi_bresp!=2) $fatal(1,"readonly write response");
  read_word(0,32'h5a325643);
  $display("PASS: observer MMIO, backpressure and independent readonly writes");$finish;
 end
 initial begin #20000;$fatal(1,"timeout");end
endmodule
