`timescale 1ns/1ps
// Bundled-data handshake; source data is held until destination acknowledges.
module visual_mailbox #(parameter WIDTH=48)(
 input wire src_clk,src_rst,input wire [WIDTH-1:0] src_data,
 input wire dst_clk,dst_rst,output reg [WIDTH-1:0] dst_data);
 reg [WIDTH-1:0] held;
 reg request,ack;
 (* ASYNC_REG="TRUE" *) reg [1:0] req_sync,ack_sync;
 always @(posedge src_clk)begin
  if(src_rst)begin held<=0;request<=0;ack_sync<=0;end
  else begin
   ack_sync<={ack_sync[0],ack};
   if(request==ack_sync[1])begin held<=src_data;request<=!request;end
  end
 end
 always @(posedge dst_clk)begin
  if(dst_rst)begin req_sync<=0;ack<=0;dst_data<=0;end
  else begin
   req_sync<={req_sync[0],request};
   if(req_sync[1]!=ack)begin dst_data<=held;ack<=req_sync[1];end
  end
 end
endmodule
