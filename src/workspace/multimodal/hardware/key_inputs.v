`timescale 1ns/1ps
module key_inputs(
 (* X_INTERFACE_PARAMETER="ASSOCIATED_RESET aresetn, FREQ_HZ 100000000" *)
 (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 aclk CLK" *) input wire aclk,
 (* X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *)
 (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 aresetn RST" *) input wire aresetn,
 input wire [1:0] keys,output wire [1:0] value
);
 (* ASYNC_REG="TRUE" *) reg [1:0] meta,sync;
 always @(posedge aclk)begin
  if(!aresetn)begin meta<=2'b11;sync<=2'b11;end
  else begin meta<=keys;sync<=meta;end
 end
 assign value=sync;
endmodule
