`timescale 1ns/1ps
module tb_signal;
reg clk=0,rst=0; always #5 clk=~clk;
reg [31:0] in_data=0; reg valid=0,last=0; wire ready;
wire [31:0] out_data; wire out_valid,out_last; reg out_ready=1;
signal_core dut(.aclk(clk),.aresetn(rst),.s_axis_tdata(in_data),.s_axis_tvalid(valid),.s_axis_tready(ready),.s_axis_tlast(last),
 .m_axis_tdata(out_data),.m_axis_tvalid(out_valid),.m_axis_tready(out_ready),.m_axis_tlast(out_last),
 .s_axi_awaddr(8'd0),.s_axi_awvalid(1'b0),.s_axi_wdata(32'd0),.s_axi_wstrb(4'd0),.s_axi_wvalid(1'b0),.s_axi_bready(1'b1),
 .s_axi_araddr(8'd0),.s_axi_arvalid(1'b0),.s_axi_rready(1'b1));
initial begin
 #25; rst=1;
 @(negedge clk); valid=1; in_data=1000; last=1;
 @(negedge clk); valid=0;
 if(!out_valid || $signed(out_data)!=250 || !out_last) $fatal(1,"known IIR impulse expected 250");
 out_ready=0;
 @(negedge clk); if(out_data!=250 || !out_valid || ready) $fatal(1,"backpressure stability");
 out_ready=1; @(negedge clk); valid=1; in_data=0; last=0;
 @(negedge clk); valid=0;
 if($signed(out_data)!=187) $fatal(1,"independent second sample expected 187");
 rst=0; @(negedge clk); rst=1; @(negedge clk);
 valid=1; in_data=1000;
 @(negedge clk); valid=0;
 if($signed(out_data)!=250) $fatal(1,"reset clears filter history");
 $display("AXIS known-reference, backpressure, TLAST and reset PASS"); $finish;
end
initial begin #10000; $fatal(1,"timeout"); end
endmodule
