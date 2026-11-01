// Navigator ES8388 capture. Playback requires an explicit build-time opt-in.
// The codec register and I2S engines are loaded from the pinned vendor example 37.
module navigator_audio_core #(parameter PLAYBACK_ENABLED = 0)(
    input sys_clk,
    input sys_rst_n,
    input key,
    output aud_lrc,
    output aud_bclk,
    input aud_adcdat,
    output aud_mclk,
    output aud_dacdat,
    output aud_scl,
    inout aud_sda,
    output wire signed [15:0] monitor_sample,
    output wire monitor_valid
);
    wire locked;
    wire run_reset_n = sys_rst_n && locked;
    wire [15:0] adc_data;
    wire rx_done;
    wire signed [15:0] tone_sample;
    reg signed [15:0] loop_sample;
    reg key_meta, key_sync;
    wire signed [15:0] output_sample = key_sync ? tone_sample : loop_sample;
    assign monitor_sample = $signed(adc_data);
    assign monitor_valid = rx_done && !aud_lrc;

    clk_wiz_0 u_clk_wiz(
        .clk_in1(sys_clk), .reset(~sys_rst_n), .clk_out1(aud_mclk), .locked(locked)
    );
    slave_signal_gen u_clocks(
        .clk(aud_mclk), .rst_n(run_reset_n), .aud_bclk(aud_bclk), .aud_lrc(aud_lrc)
    );
    audio_config u_codec(
        .clk(sys_clk), .rst_n(run_reset_n), .aud_scl(aud_scl), .aud_sda(aud_sda)
    );
    audio_receive u_rx(
        .rst_n(run_reset_n), .aud_bclk(aud_bclk), .aud_lrc(aud_lrc),
        .aud_adcdat(aud_adcdat), .rx_done(rx_done), .adc_data(adc_data)
    );
    generate
        if (PLAYBACK_ENABLED) begin : g_playback
            audio_send u_tx(
                .rst_n(run_reset_n), .aud_bclk(aud_bclk), .aud_lrc(aud_lrc),
                .dac_data(output_sample), .aud_dacdat(aud_dacdat), .tx_done()
            );
        end else begin : g_silent
            assign aud_dacdat = 1'b0;
        end
    endgenerate
    tone_1khz u_tone(
        .clk(aud_bclk), .rst_n(run_reset_n),
        .sample_tick(rx_done && !aud_lrc), .sample(tone_sample)
    );

    always @(posedge aud_bclk or negedge run_reset_n) begin
        if (!run_reset_n) begin
            loop_sample <= 16'sd0;
            key_meta <= 1'b1;
            key_sync <= 1'b1;
        end else begin
            key_meta <= key;
            key_sync <= key_meta;
            if (rx_done)
                loop_sample <= $signed(adc_data) >>> 2;
        end
    end
endmodule

module navigator_audio_demo(
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
    inout aud_sda
);
    assign beep = 1'b0;
    navigator_audio_core u_audio(
        .sys_clk(sys_clk), .sys_rst_n(sys_rst_n), .key(key),
        .aud_lrc(aud_lrc), .aud_bclk(aud_bclk), .aud_adcdat(aud_adcdat),
        .aud_mclk(aud_mclk), .aud_dacdat(aud_dacdat),
        .aud_scl(aud_scl), .aud_sda(aud_sda),
        .monitor_sample(), .monitor_valid()
    );
endmodule
