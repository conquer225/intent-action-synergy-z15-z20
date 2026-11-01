// Peak meter with held-payload request/ack transfer from BCLK to pixel clock.
module audio_meter_cdc #(
    parameter integer BLOCK_SAMPLES = 256,
    parameter integer COUNT_BITS = 8
)(
    input audio_clk,
    input pixel_clk,
    input rst_n,
    input sample_valid,
    input signed [15:0] sample,
    output reg [7:0] level
);
    reg [COUNT_BITS-1:0] count;
    reg [15:0] peak;
    reg [7:0] payload;
    reg request;
    reg ack_meta, ack_sync;
    reg request_meta, request_sync, request_seen, ack;
    wire [15:0] magnitude = sample[15] ? -sample : sample;
    wire [15:0] block_peak = magnitude > peak ? magnitude : peak;

    always @(posedge audio_clk or negedge rst_n) begin
        if (!rst_n) begin
            count <= 0;
            peak <= 0;
            payload <= 0;
            request <= 0;
            ack_meta <= 0;
            ack_sync <= 0;
        end else begin
            ack_meta <= ack;
            ack_sync <= ack_meta;
            if (sample_valid) begin
                if (count == BLOCK_SAMPLES - 1) begin
                    count <= 0;
                    peak <= 0;
                    if (request == ack_sync) begin
                        payload <= block_peak > 16'd8160 ? 8'd255 : block_peak[12:5];
                        request <= ~request;
                    end
                end else begin
                    count <= count + 1'b1;
                    peak <= block_peak;
                end
            end
        end
    end

    always @(posedge pixel_clk or negedge rst_n) begin
        if (!rst_n) begin
            request_meta <= 0;
            request_sync <= 0;
            request_seen <= 0;
            ack <= 0;
            level <= 0;
        end else begin
            request_meta <= request;
            request_sync <= request_meta;
            if (request_sync != request_seen) begin
                level <= payload;
                request_seen <= request_sync;
                ack <= request_sync;
            end
        end
    end
endmodule
