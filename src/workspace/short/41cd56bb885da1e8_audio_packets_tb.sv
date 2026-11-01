`timescale 1ns/1fs
module audio_packets_tb #(parameter EXTERNAL_VIDEO = 0);
    logic clk150 = 0, pixel = 0, reset = 1;
    always #(10.0/3.0) clk150 = !clk150;
    always #(20.0/3.0) pixel = !pixel;
    wire sample_clk;
    audio_sample_clock clock_source (.clk_150m(clk150), .reset(reset), .clk_sample(sample_clk));
    wire tick;
    audio_sample_tick tick_source (.clk_pixel(pixel), .reset(reset), .sample_enable(tick));
    logic [15:0] enabled_samples [1:0] = '{16'hffff,16'd1};
    integer pixel_cycles=0,last_tick=0,tick_count=0;
    always @(posedge pixel) if (!reset) begin
        pixel_cycles++;
        if (tick) begin
            if (last_tick && pixel_cycles-last_tick!=1562 && pixel_cycles-last_tick!=1563)
                $fatal(1,"Incorrect sample-enable interval");
            last_tick=pixel_cycles;tick_count++;
            enabled_samples[0] <= enabled_samples[0]+1'b1;
            enabled_samples[1] <= enabled_samples[1]-1'b1;
        end
        if (pixel_cycles%75000==0 && tick_count!=48*(pixel_cycles/75000))
            $fatal(1,"Not exactly 48000 samples per second");
    end

    logic [15:0] samples [1:0] = '{16'hffff, 16'd1};
    always @(negedge sample_clk) if (!reset) begin
        samples[0] <= samples[0] + 1'b1;
        samples[1] <= samples[1] - 1'b1;
    end
    integer source_cycles = 0, previous_edge = 0, clock_checks = 0;
    always @(posedge clk150) source_cycles <= source_cycles + 1;
    always @(posedge sample_clk) begin
        if (previous_edge) begin
            if (source_cycles - previous_edge != 3125) $fatal(1, "Incorrect 48 kHz divider");
            clock_checks++;
        end
        previous_edge = source_cycles;
    end

    logic [10:0] x = 0;
    logic [9:0] y = 0;
    always @(posedge pixel) begin
        if (reset) begin x <= 0; y <= 0; end
        else begin
            x <= x == 1649 ? 0 : x + 1'b1;
            if (x == 1649) y <= y == 749 ? 0 : y + 1'b1;
        end
    end
    wire island_now = x >= 1294 && x < 1614;
    wire packet_enable = island_now && ((x - 1294) % 32 == 0);
    logic island = 0;
    always @(posedge pixel) island <= !reset && island_now;
    wire [4:0] packet_counter;
    wire [8:0] packet_data;
    wire monitor_island;
    integer video_pixels = 0;
    if (!EXTERNAL_VIDEO) begin: packet_only
        wire [23:0] selected_header;
        wire [55:0] selected_sub [3:0];
        assign monitor_island = island;
        packet_picker #(.VIDEO_ID_CODE(4), .VIDEO_RATE(75.0e6), .IT_CONTENT(1),
        .AUDIO_BIT_WIDTH(16), .AUDIO_RATE(48000), .VENDOR_NAME("GL      "),
        .PRODUCT_DESCRIPTION("Z15 HDMI AUDIO  ")) picker (
        .clk_pixel(pixel), .clk_audio(sample_clk), .audio_enable(1'b1), .reset(reset), .video_field_end(1'b0),
        .packet_enable(packet_enable), .packet_pixel_counter(packet_counter),
        .audio_sample_word(samples), .header(selected_header), .sub(selected_sub));
        packet_assembler assembler (.clk_pixel(pixel), .reset(reset), .data_island_period(island),
        .header(selected_header), .sub(selected_sub), .packet_data(packet_data), .counter(packet_counter));
    end else begin: external_video
        wire [9:0] words [2:0];
        wire [29:0] packed_words;
        for (genvar c=0;c<3;c++) assign words[c]=packed_words[c*10+:10];
        wire locked;
        wire hs = x >= 1390 && x < 1430;
        // Current HWH VTC starts vertical sync at line 724, not the upstream core's 725.
        wire vs = y >= 724 && y < 729;
        wire de = x < 1280 && y < 720;
        wire [23:0] rgb = {x[7:0],y[7:0],(x[7:0] ^ y[7:0])};
        hdmi_external_video dut (.clk_pixel(pixel), .sample_enable(tick), .reset(reset),
            .rgb(rgb), .hsync(hs), .vsync(vs), .de(de), .sample_left(enabled_samples[0]),
            .sample_right(enabled_samples[1]), .timing_locked(locked), .tmds_words(packed_words));
        logic [10:0] xd [2:0];
        logic [9:0] yd [2:0];
        logic [23:0] colors [2:0];
        logic [2:0] de_pipe = 0, hs_pipe = 0, vs_pipe = 0, lock_pipe = 0;
        always @(posedge pixel) begin
            xd[0] <= x; xd[1] <= xd[0]; xd[2] <= xd[1];
            yd[0] <= y; yd[1] <= yd[0]; yd[2] <= yd[1];
            colors[0] <= rgb; colors[1] <= colors[0]; colors[2] <= colors[1];
            de_pipe <= {de_pipe[1:0],de}; hs_pipe <= {hs_pipe[1:0],hs};
            vs_pipe <= {vs_pipe[1:0],vs}; lock_pipe <= {lock_pipe[1:0],locked};
        end
        function automatic [3:0] decode_terc4(input [9:0] code);
            case (code)
                10'b1010011100: decode_terc4 = 0;
                10'b1001100011: decode_terc4 = 1;
                10'b1011100100: decode_terc4 = 2;
                10'b1011100010: decode_terc4 = 3;
                10'b0101110001: decode_terc4 = 4;
                10'b0100011110: decode_terc4 = 5;
                10'b0110001110: decode_terc4 = 6;
                10'b0100111100: decode_terc4 = 7;
                10'b1011001100: decode_terc4 = 8;
                10'b0100111001: decode_terc4 = 9;
                10'b0110011100: decode_terc4 = 10;
                10'b1011000110: decode_terc4 = 11;
                10'b1010001110: decode_terc4 = 12;
                10'b1001110001: decode_terc4 = 13;
                10'b0101100011: decode_terc4 = 14;
                10'b1011000011: decode_terc4 = 15;
                default: decode_terc4 = 4'bxxxx;
            endcase
        endfunction
        function automatic [7:0] decode_video(input [9:0] code);
            reg [7:0] q;
            begin
                q = code[9] ? ~code[7:0] : code[7:0];
                decode_video[0] = q[0];
                for (int b = 1; b < 8; b++)
                    decode_video[b] = code[8] ? (q[b] ^ q[b-1]) : (q[b] ~^ q[b-1]);
            end
        endfunction
        function automatic [9:0] control_code(input [1:0] value);
            case (value)
                0: control_code = 10'b1101010100;
                1: control_code = 10'b0010101011;
                2: control_code = 10'b0101010100;
                3: control_code = 10'b1010101011;
            endcase
        endfunction
        wire [3:0] nibble0 = decode_terc4(words[0]);
        wire [3:0] nibble1 = decode_terc4(words[1]);
        wire [3:0] nibble2 = decode_terc4(words[2]);
        assign monitor_island = lock_pipe[2] && xd[2] >= 1294 && xd[2] < 1614;
        assign packet_counter = 5'(xd[2] - 1294);
        assign packet_data = {nibble2,nibble1,nibble0[2]};
        always @(negedge pixel) if (!reset && $time > 2000) begin
            if (de_pipe[2]) begin
                if ({decode_video(words[2]),decode_video(words[1]),decode_video(words[0])} !== colors[2])
                    $fatal(1, "Video pixel changed at %0d,%0d", xd[2], yd[2]);
                video_pixels++;
            end else if (monitor_island) begin
                if ($isunknown({nibble0,nibble1,nibble2}) || nibble0[1:0] !== {vs_pipe[2],hs_pipe[2]})
                    $fatal(1, "Invalid TERC4 or sync bits");
            end else if (lock_pipe[2] && ((xd[2] >= 1292 && xd[2] < 1294) ||
                                         (xd[2] >= 1614 && xd[2] < 1616))) begin
                if (words[2] !== 10'b0100110011 || words[1] !== 10'b0100110011 ||
                    decode_terc4(words[0]) !== {2'b11,vs_pipe[2],hs_pipe[2]})
                    $fatal(1, "Data-island guard changed");
            end else if (lock_pipe[2] && xd[2] >= 1648 && (yd[2] < 719 || yd[2] == 749)) begin
                if (words[0] !== 10'b1011001100 || words[1] !== 10'b0100110011 || words[2] !== 10'b1011001100)
                    $fatal(1, "Video guard changed");
            end else begin
                if (words[0] !== control_code({vs_pipe[2],hs_pipe[2]})) $fatal(1, "HS/VS not preserved");
                if (words[2] !== control_code({1'b0,(lock_pipe[2] && xd[2] >= 1284 && xd[2] < 1292)}))
                    $fatal(1, "Data-island preamble changed");
                if (words[1] !== control_code({1'b0,(lock_pipe[2] && ((xd[2] >= 1284 && xd[2] < 1292) ||
                    (xd[2] >= 1640 && xd[2] < 1648 && (yd[2] < 719 || yd[2] == 749))))}))
                    $fatal(1, "Video/island preamble changed");
            end
        end
    end

    // Decode transmitted packet bits; expected PCM and IEC status are independent of DUT internals.
    logic [31:0] received_header = 0;
    logic [63:0] received_sub [3:0];
    logic [191:0] status_left = 0, status_right = 0;
    logic [15:0] previous_sample = 0;
    integer sample_count = 0, audio_packets = 0, acr_packets = 0;
    integer avi_packets = 0, spd_packets = 0, info_packets = 0, status_blocks = 0;
    integer iec_frame = 0;

    function automatic [7:0] ecc_step(input [7:0] state, input bit value);
        ecc_step = (state >> 1) ^ ((state[0] ^ value) ? 8'h83 : 8'd0);
    endfunction

    task automatic check_packet;
        reg [7:0] ecc;
        integer checksum, n, cts;
        begin
            ecc = 0;
            for (int b = 0; b < 32; b++) ecc = ecc_step(ecc, received_header[b]);
            if (ecc !== 0) $fatal(1, "Header BCH mismatch");
            for (int s = 0; s < 4; s++) begin
                ecc = 0;
                for (int b = 0; b < 64; b++) ecc = ecc_step(ecc, received_sub[s][b]);
                if (ecc !== 0) $fatal(1, "Payload BCH mismatch");
            end
            case (received_header[7:0])
                0: ;
                1: begin
                    n = {received_sub[0][35:32], received_sub[0][47:40], received_sub[0][55:48]};
                    cts = {received_sub[0][11:8], received_sub[0][23:16], received_sub[0][31:24]};
                    if (n != 6144) $fatal(1, "Incorrect ACR N=%0d", n);
                    // First ACR spans only the partial interval after reset.
                    if (acr_packets && (cts < 74999 || cts > 75001))
                        $fatal(1, "Incorrect ACR CTS=%0d at 75 MHz", cts);
                    for (int s = 1; s < 4; s++)
                        if (received_sub[s] !== received_sub[0]) $fatal(1, "ACR copies differ");
                    $display("ACR N=%0d CTS=%0d", n, cts);
                    acr_packets++;
                end
                2: begin
                    if (received_header[19:8] !== 12'h00f) $fatal(1, "Not stereo four-sample PCM");
                    for (int s = 0; s < 4; s++) begin
                        if ($isunknown(received_sub[s])) $fatal(1, "Unknown PCM bits");
                        if (received_sub[s][7:0] != 0 || received_sub[s][31:24] != 0)
                            $fatal(1, "PCM16 is not aligned to 24-bit container");
                        if (sample_count && received_sub[s][23:8] !== previous_sample + 16'd1)
                            $fatal(1, "Lost/reordered PCM: previous=%0d current=%0d", previous_sample, received_sub[s][23:8]);
                        if (received_sub[s][47:32] !== 16'(-$signed(received_sub[s][23:8])))
                            $fatal(1, "Left/right swap or corrupt stereo");
                        if (^{received_sub[s][51:48], received_sub[s][23:0]} !== 1'b0 ||
                            ^{received_sub[s][55:52], received_sub[s][47:24]} !== 1'b0)
                            $fatal(1, "IEC parity mismatch");
                        if (received_sub[s][49:48] != 0 || received_sub[s][53:52] != 0)
                            $fatal(1, "Invalid LPCM user/valid flags");
                        if (received_header[20+s] !== (iec_frame == 0)) $fatal(1, "IEC block boundary mismatch");
                        status_left[iec_frame] = received_sub[s][50];
                        status_right[iec_frame] = received_sub[s][54];
                        previous_sample = received_sub[s][23:8];
                        sample_count++;
                        iec_frame++;
                        if (iec_frame == 192) begin
                            if (status_left !== 192'h0000000202100004 || status_right !== 192'h0000000202200004)
                                $fatal(1, "IEC channel status incorrect L=%h R=%h", status_left, status_right);
                            status_blocks++;
                            iec_frame = 0;
                        end
                    end
                    audio_packets++;
                end
                8'h82, 8'h83, 8'h84: begin
                    checksum = received_header[7:0] + int'(received_header[15:8]) + int'(received_header[23:16]);
                    for (int s = 0; s < 4; s++)
                        for (int b = 0; b < 7; b++) checksum += received_sub[s][b*8+:8];
                    if ((checksum & 255) != 0) $fatal(1, "InfoFrame checksum mismatch");
                    case (received_header[7:0])
                        8'h82: begin
                            if (received_sub[0][39:32] != 4) $fatal(1, "AVI is not 720p VIC4");
                            avi_packets++;
                        end
                        8'h83: spd_packets++;
                        8'h84: begin
                            if (received_header[23:8] != 16'h0a01 || received_sub[0][15:8] != 1)
                                $fatal(1, "Audio InfoFrame is not 2-channel");
                            info_packets++;
                        end
                    endcase
                end
                default: $fatal(1, "Unknown packet type");
            endcase
        end
    endtask

    always @(negedge pixel) if (!reset && monitor_island) begin
        received_header[packet_counter] = packet_data[0];
        for (int s = 0; s < 4; s++) begin
            received_sub[s][2*packet_counter] = packet_data[1+s];
            received_sub[s][2*packet_counter+1] = packet_data[5+s];
        end
        if (packet_counter == 31) check_packet();
    end
    initial begin
        #1005 reset = 0;
        #(EXTERNAL_VIDEO ? 34000000 : 7000000);
        if (sample_count < 320 || acr_packets < 6 || !status_blocks || !clock_checks ||
            !avi_packets || !spd_packets || !info_packets) $fatal(1, "Incomplete packet coverage");
        if (EXTERNAL_VIDEO && video_pixels < 1843200) $fatal(1, "Incomplete video coverage");
        $display("AUDIO_PACKETS_PASS samples=%0d audio_packets=%0d acr=%0d IEC_blocks=%0d video_pixels=%0d 48kHz=PASS BCH=PASS InfoFrames=PASS", sample_count, audio_packets, acr_packets, status_blocks, video_pixels);
        $finish;
    end
endmodule

module hdmi_external_tb;
    audio_packets_tb #(.EXTERNAL_VIDEO(1)) test();
endmodule
