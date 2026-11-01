`timescale 1ns/1ps
// 1280x720 / 1650x750 adapter for the existing VTC output. Packet/encoding
// primitives remain hdl-util/hdmi (MIT OR Apache-2.0); this module owns no VTC.
module hdmi_external_video (
    input wire clk_pixel,
    input wire sample_enable,
    input wire reset,
    input wire [23:0] rgb,
    input wire hsync,
    input wire vsync,
    input wire de,
    input wire [15:0] sample_left,
    input wire [15:0] sample_right,
    output logic timing_locked = 0,
    output wire [29:0] tmds_words
);
    logic last_hsync = 0, last_vsync = 0, last_de = 0;
    logic seen_hsync = 0, seen_vsync = 0;
    logic [10:0] next_x = 0;
    logic [9:0] next_y = 0;
    wire falling_hsync = last_hsync && !hsync;
    wire first_active = de && !last_de && seen_vsync;
    wire [10:0] x = falling_hsync ? 11'd1430 : next_x;
    wire [9:0] y = first_active ? 10'd0 : next_y;
    always @(posedge clk_pixel) begin
        if (reset) begin
            next_x <= 0; next_y <= 0;
            last_hsync <= 0; last_vsync <= 0; last_de <= 0;
            seen_hsync <= 0; seen_vsync <= 0; timing_locked <= 0;
        end else begin
            last_hsync <= hsync; last_vsync <= vsync; last_de <= de;
            next_x <= x == 1649 ? 11'd0 : x + 1'b1;
            next_y <= x == 1649 ? (y == 749 ? 10'd0 : y + 1'b1) : y;
            if (falling_hsync) seen_hsync <= 1;
            if (vsync && !last_vsync) seen_vsync <= 1;
            if (first_active) begin
                seen_vsync <= 0;
                timing_locked <= seen_hsync && x == 0;
            end else if (timing_locked && de != (x < 1280 && y < 720))
                timing_locked <= 0;
        end
    end

    wire island_now = timing_locked && x >= 1294 && x < 1614;
    wire packet_enable = island_now && ((x - 1294) & 31) == 0;
    logic island_d = 0, guard_d = 0, preamble_d = 0;
    logic video_guard_d = 0, video_preamble_d = 0;
    logic de_d = 0, hsync_d = 0, vsync_d = 0;
    logic [23:0] rgb_d = 0;
    always @(posedge clk_pixel) begin
        if (reset) begin
            island_d <= 0; guard_d <= 0; preamble_d <= 0;
            video_guard_d <= 0; video_preamble_d <= 0;
            de_d <= 0; hsync_d <= 0; vsync_d <= 0; rgb_d <= 0;
        end else begin
            island_d <= island_now;
            guard_d <= timing_locked && ((x >= 1292 && x < 1294) || (x >= 1614 && x < 1616));
            preamble_d <= timing_locked && x >= 1284 && x < 1292;
            video_guard_d <= timing_locked && x >= 1648 && (y < 719 || y == 749);
            video_preamble_d <= timing_locked && x >= 1640 && x < 1648 && (y < 719 || y == 749);
            de_d <= de; hsync_d <= hsync; vsync_d <= vsync; rgb_d <= rgb;
        end
    end
    wire [15:0] audio_samples [1:0];
    assign audio_samples[0] = sample_left;
    assign audio_samples[1] = sample_right;
    wire [23:0] header;
    wire [55:0] sub [3:0];
    wire [4:0] packet_counter;
    wire [8:0] packet_data;
    packet_picker #(.VIDEO_ID_CODE(4), .VIDEO_RATE(75.0e6), .IT_CONTENT(1),
        .AUDIO_BIT_WIDTH(16), .AUDIO_RATE(48000), .USE_AUDIO_ENABLE(1), .VENDOR_NAME("GL      "),
        .PRODUCT_DESCRIPTION("Z15 HDMI AUDIO  ")) picker (
        .clk_pixel(clk_pixel), .clk_audio(clk_pixel), .audio_enable(sample_enable), .reset(reset || !timing_locked),
        .video_field_end(timing_locked && x == 1279 && y == 719),
        .packet_enable(packet_enable), .packet_pixel_counter(packet_counter),
        .audio_sample_word(audio_samples), .header(header), .sub(sub));
    packet_assembler assembler (.clk_pixel(clk_pixel), .reset(reset || !timing_locked),
        .data_island_period(island_d), .header(header), .sub(sub),
        .packet_data(packet_data), .counter(packet_counter));

    logic [2:0] mode = 0;
    logic [23:0] video_data = 0;
    logic [5:0] control_data = 0;
    logic [11:0] island_data = 0;
    always @(posedge clk_pixel) begin
        if (reset) begin mode <= 0; video_data <= 0; control_data <= 0; island_data <= 0; end
        else begin
            mode <= guard_d ? 4 : island_d ? 3 : video_guard_d ? 2 : de_d ? 1 : 0;
            video_data <= rgb_d;
            control_data <= {1'b0,preamble_d,1'b0,(video_preamble_d || preamble_d),vsync_d,hsync_d};
            island_data <= island_d ? {packet_data[8:1], 1'b1, packet_data[0], vsync_d, hsync_d} : 12'd0;
        end
    end
    for (genvar c = 0; c < 3; c++) begin: channels
        tmds_channel #(.CN(c)) encoder (.clk_pixel(clk_pixel),
            .video_data(video_data[c*8+:8]), .data_island_data(island_data[c*4+:4]),
            .control_data(control_data[c*2+:2]), .mode(mode), .tmds(tmds_words[c*10+:10]));
    end
endmodule
