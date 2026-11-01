`timescale 1ns/1ps
// Fixed 10-sample x 8-channel DMA frame. No board clock/AXI-Lite integration.
module primary_sos_axis (
    input wire aclk, input wire areset,
    input wire [63:0] s_axis_tdata,
    input wire [7:0] s_axis_tkeep,
    input wire s_axis_tlast, input wire s_axis_tvalid,
    output wire s_axis_tready,
    output wire [63:0] m_axis_tdata,
    output wire [7:0] m_axis_tkeep,
    output wire m_axis_tlast, output wire m_axis_tvalid,
    input wire m_axis_tready,
    output wire fault
);
    reg [6:0] word_index;
    reg pending_last;
    reg frame_fault;
    wire core_ready, core_valid, core_overflow;
    wire [2:0] core_channel;
    wire signed [39:0] core_data;
    wire expected_last = word_index == 79;
    wire format_ok = s_axis_tkeep == 8'hff && s_axis_tlast == expected_last &&
                     s_axis_tdata[63:40] == {24{s_axis_tdata[39]}};
    assign fault = frame_fault | core_overflow;
    assign s_axis_tready = core_ready && !fault && !areset;
    assign m_axis_tdata = {{24{core_data[39]}},core_data};
    assign m_axis_tkeep = 8'hff;
    assign m_axis_tlast = pending_last;
    assign m_axis_tvalid = core_valid && !fault && !areset;
    primary_sos_core core (
        .clk(aclk), .rst(areset | frame_fault),
        .in_valid(s_axis_tvalid && format_ok && !fault), .in_ready(core_ready),
        .in_channel(word_index[2:0]), .in_data(s_axis_tdata[39:0]),
        .out_valid(core_valid), .out_ready(m_axis_tready && !fault),
        .out_channel(core_channel), .out_data(core_data), .overflow(core_overflow)
    );
    always @(posedge aclk) begin
        if (areset) begin
            word_index <= 0;
            pending_last <= 0;
            frame_fault <= 0;
        end else if (fault) begin
            frame_fault <= 1; // Fail closed until explicit reset, never silently resynchronise.
        end else if (s_axis_tvalid && s_axis_tready) begin
            if (!format_ok) frame_fault <= 1;
            else begin
                pending_last <= expected_last;
                word_index <= expected_last ? 0 : word_index+1;
            end
        end
    end
endmodule
