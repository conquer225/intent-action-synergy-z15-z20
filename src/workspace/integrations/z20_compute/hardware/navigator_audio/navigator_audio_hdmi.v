// Continuous I2S audio and HDMI scan; the peak meter only observes samples.
module navigator_audio_hdmi(
    input sys_clk,
    input sys_rst_n,
    input key,
    output beep,
    output aud_lrc,
    output aud_bclk,
    input aud_adcdat,
    output aud_mclk,
    output aud_dacdat,
    output aud_scl,
    inout aud_sda,
    output tmds_clk_p,
    output tmds_clk_n,
    output [2:0] tmds_data_p,
    output [2:0] tmds_data_n
);
    wire signed [15:0] sample;
    wire sample_valid;
    wire pixel_clk, pixel_clk_5x, video_locked;
    wire [7:0] level;
    wire [10:0] pixel_xpos, pixel_ypos;
    wire [23:0] pixel_data, video_rgb;
    wire video_hs, video_vs, video_de;
    assign beep = 1'b0;

    navigator_audio_core u_audio(
        .sys_clk(sys_clk), .sys_rst_n(sys_rst_n), .key(key),
        .aud_lrc(aud_lrc), .aud_bclk(aud_bclk), .aud_adcdat(aud_adcdat),
        .aud_mclk(aud_mclk), .aud_dacdat(aud_dacdat),
        .aud_scl(aud_scl), .aud_sda(aud_sda),
        .monitor_sample(sample), .monitor_valid(sample_valid)
    );
    clk_wiz_video u_video_clk(
        .clk_in1(sys_clk), .reset(~sys_rst_n),
        .clk_out1(pixel_clk), .clk_out2(pixel_clk_5x), .locked(video_locked)
    );
    audio_meter_cdc u_meter(
        .audio_clk(aud_bclk), .pixel_clk(pixel_clk), .rst_n(sys_rst_n && video_locked),
        .sample_valid(sample_valid), .sample(sample), .level(level)
    );
    video_driver u_video_driver(
        .pixel_clk(pixel_clk), .sys_rst_n(sys_rst_n && video_locked),
        .video_hs(video_hs), .video_vs(video_vs), .video_de(video_de),
        .video_rgb(video_rgb), .data_req(),
        .pixel_xpos(pixel_xpos), .pixel_ypos(pixel_ypos), .pixel_data(pixel_data)
    );
    audio_level_display u_display(
        .pixel_clk(pixel_clk), .rst_n(sys_rst_n && video_locked),
        .pixel_xpos(pixel_xpos), .pixel_ypos(pixel_ypos), .level(level),
        .pixel_data(pixel_data)
    );
    dvi_transmitter_top u_hdmi(
        .pclk(pixel_clk), .pclk_x5(pixel_clk_5x), .reset_n(sys_rst_n && video_locked),
        .video_din(video_rgb), .video_hsync(video_hs), .video_vsync(video_vs),
        .video_de(video_de), .tmds_clk_p(tmds_clk_p), .tmds_clk_n(tmds_clk_n),
        .tmds_data_p(tmds_data_p), .tmds_data_n(tmds_data_n), .tmds_oen()
    );
endmodule
