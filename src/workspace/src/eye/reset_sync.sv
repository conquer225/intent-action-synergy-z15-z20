`timescale 1ns/1ps
module reset_sync(input wire clk,arst,output wire rst);
 (* ASYNC_REG="TRUE" *) reg [2:0] pipe=3'b111;
 always @(posedge clk or posedge arst)if(arst)pipe<=3'b111;else pipe<={pipe[1:0],1'b0};
 assign rst=pipe[2];
endmodule
