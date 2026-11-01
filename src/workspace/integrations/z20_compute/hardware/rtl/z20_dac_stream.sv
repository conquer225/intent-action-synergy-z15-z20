// Clock-domain contract: clk, sample_tick and AXIS all share one PL clock.
// Converter clock forwarding/timing constraints belong in the reviewed board design.
// TDATA[7:0] is unsigned DAC code; TDATA[8] is spectrum sweep-start marker.
module z20_dac_stream (
    input wire clk,
    input wire resetn,
    input wire sample_tick,
    input wire [8:0] s_axis_tdata,
    input wire s_axis_tvalid,
    output wire s_axis_tready,
    output reg [7:0] dac_data,
    output reg sweep_sync,
    output reg underrun,
    output reg [31:0] underrun_count
);
    assign s_axis_tready = resetn && sample_tick;
    always @(posedge clk) begin
        if (!resetn) begin
            dac_data <= 8'd128;
            sweep_sync <= 1'b0;
            underrun <= 1'b0;
            underrun_count <= 32'd0;
        end else begin
            // Data/marker hold between converter sample strobes.
            underrun <= 1'b0;
            if (sample_tick) begin
                dac_data <= s_axis_tvalid ? s_axis_tdata[7:0] : 8'd128;
                sweep_sync <= s_axis_tvalid && s_axis_tdata[8];
                if (!s_axis_tvalid) begin
                    underrun <= 1'b1;
                    if (underrun_count != 32'hffffffff)
                        underrun_count <= underrun_count+1'b1;
                end
            end
        end
    end
endmodule
