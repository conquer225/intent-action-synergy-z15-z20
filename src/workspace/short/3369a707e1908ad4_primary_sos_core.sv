`timescale 1ns/1ps
// Isolated simulation candidate. No AXI, clock pin, or board integration yet.
module primary_sos_core (
    input wire clk,
    input wire rst,
    input wire in_valid,
    output wire in_ready,
    input wire [2:0] in_channel,
    input wire signed [39:0] in_data,
    output reg out_valid,
    input wire out_ready,
    output reg [2:0] out_channel,
    output reg signed [39:0] out_data,
    output reg overflow
);
    localparam IDLE=0, Y=1, B1=2, A1=3, B2=4, A2=5, HOLD=6;
    reg [2:0] state;
    reg [2:0] stage_index;
    reg [2:0] channel;
    reg signed [39:0] x, y_value;
    reg signed [39:0] z1[0:39];
    reg signed [39:0] z2[0:39];
    reg signed [33:0] coeff[0:24];
    reg signed [75:0] partial;
    reg signed [39:0] mul_data;
    reg signed [33:0] mul_coeff;
    wire signed [73:0] product = mul_data * mul_coeff;
    wire signed [75:0] wide_product = {{2{product[73]}}, product};
    wire [5:0] slot = {stage_index, channel};
    wire signed [75:0] state1 = {{36{z1[slot][39]}}, z1[slot]};
    wire signed [75:0] state2 = {{36{z2[slot][39]}}, z2[slot]};
    reg signed [75:0] accumulator, rounded;
    localparam signed [75:0] HALF = 76'sd1073741824;
    localparam signed [75:0] MAX_DATA = 76'sd549755813887;
    localparam signed [75:0] MIN_DATA = -76'sd549755813888;
    wire clipped = (rounded > MAX_DATA) || (rounded < MIN_DATA);
    wire signed [39:0] narrowed = rounded > MAX_DATA ? 40'sh7fffffffff :
                                 rounded < MIN_DATA ? 40'sh8000000000 : rounded[39:0];
    assign in_ready = state == IDLE && !rst;
    integer k;
    initial $readmemh("coeff.hex", coeff);

    always @* begin
        mul_data = x;
        mul_coeff = coeff[stage_index*5];
        case (state)
            B1: mul_coeff = coeff[stage_index*5+1];
            A1: begin mul_coeff = coeff[stage_index*5+3]; mul_data = y_value; end
            B2: mul_coeff = coeff[stage_index*5+2];
            A2: begin mul_coeff = coeff[stage_index*5+4]; mul_data = y_value; end
            default: begin end
        endcase
        accumulator = 0;
        case (state)
            Y: accumulator = wide_product + (state1 <<< 31);
            A1: accumulator = partial - wide_product + (state2 <<< 31);
            A2: accumulator = partial - wide_product;
            default: begin end
        endcase
        if (accumulator < 0)
            rounded = -(((-accumulator) + HALF) >>> 31);
        else
            rounded = (accumulator + HALF) >>> 31;
    end

    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            stage_index <= 0;
            channel <= 0;
            x <= 0;
            y_value <= 0;
            partial <= 0;
            out_valid <= 0;
            out_channel <= 0;
            out_data <= 0;
            overflow <= 0;
            for (k=0; k<40; k=k+1) begin z1[k] <= 0; z2[k] <= 0; end
        end else begin
            case (state)
                IDLE: if (in_valid) begin
                    channel <= in_channel;
                    x <= in_data;
                    stage_index <= 0;
                    state <= Y;
                end
                Y: begin
                    y_value <= narrowed;
                    if (clipped) overflow <= 1;
                    state <= B1;
                end
                B1: begin partial <= wide_product; state <= A1; end
                A1: begin
                    z1[slot] <= narrowed;
                    if (clipped) overflow <= 1;
                    state <= B2;
                end
                B2: begin partial <= wide_product; state <= A2; end
                A2: begin
                    z2[slot] <= narrowed;
                    if (clipped) overflow <= 1;
                    if (stage_index == 4) begin
                        out_data <= y_value;
                        out_channel <= channel;
                        out_valid <= 1;
                        state <= HOLD;
                    end else begin
                        x <= y_value;
                        stage_index <= stage_index + 1;
                        state <= Y;
                    end
                end
                HOLD: if (out_ready) begin out_valid <= 0; state <= IDLE; end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
