`timescale 1ns/1ps
module primary_filter_top (
    input wire aclk, input wire aresetn,
    input wire [31:0] control_word,
    output wire [31:0] status_word,
    input wire [63:0] s_axis_tdata,
    input wire [7:0] s_axis_tkeep,
    input wire s_axis_tlast, input wire s_axis_tvalid,
    output wire s_axis_tready,
    output wire [63:0] m_axis_tdata,
    output wire [7:0] m_axis_tkeep,
    output wire m_axis_tlast, output wire m_axis_tvalid,
    input wire m_axis_tready
);
    wire fault;
    wire reset_active = !aresetn || control_word[0];
    // Read via AXI GPIO channel 2: build/ABI signature plus fault/reset state.
    assign status_word = 32'h50460000 | {30'b0,fault,reset_active};
    primary_sos_axis axis_core (
        .aclk(aclk),.areset(reset_active),
        .s_axis_tdata(s_axis_tdata),.s_axis_tkeep(s_axis_tkeep),
        .s_axis_tlast(s_axis_tlast),.s_axis_tvalid(s_axis_tvalid),.s_axis_tready(s_axis_tready),
        .m_axis_tdata(m_axis_tdata),.m_axis_tkeep(m_axis_tkeep),
        .m_axis_tlast(m_axis_tlast),.m_axis_tvalid(m_axis_tvalid),.m_axis_tready(m_axis_tready),
        .fault(fault)
    );
endmodule
