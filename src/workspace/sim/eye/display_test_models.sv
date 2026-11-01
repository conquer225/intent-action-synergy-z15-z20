`timescale 1ns/1ps
// Pipeline tests isolate display device physics; never added to synthesis.
// The real TMDS encoder, scan logic, mailbox and framebuffer still run.
module display_clocks #(parameter MULT_MASTER=63.0,DIV_MASTER=5,DIV_5X=5.0,DIV_1X=25,IN_PERIOD=20.0)(
 input wire i_clk,i_rst,output reg o_clk_1x=0,output reg o_clk_5x=0,output wire o_locked);
 always #19.841 o_clk_1x=~o_clk_1x;
 always #3.968 o_clk_5x=~o_clk_5x;
 assign o_locked=!i_rst;
endmodule

module serializer_10to1(input wire i_clk,i_clk_hs,i_rst_oserdes,input wire [9:0] i_data,output wire o_data);
 // Sink only: this eye data-path test makes no TMDS electrical assertions.
 assign o_data=1'b0;
endmodule
