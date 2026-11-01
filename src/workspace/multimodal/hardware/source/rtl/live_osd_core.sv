`timescale 1ns/1ps
// Display-only geometry. Never feeds coordinates or validity back to recognition.
module live_osd_core #(
    parameter integer WIDTH=1280, HEIGHT=720, PIXEL_HZ=75000000
)(
    input wire clk, resetn,
    input wire [23:0] in_data,
    input wire in_de, in_hsync, in_vsync, in_hblank, in_vblank, in_field,
    input wire apply,
    input wire [1023:0] settings,
    output reg [23:0] out_data,
    output reg out_de, out_hsync, out_vsync, out_hblank, out_vblank, out_field,
    output reg [31:0] frame_count,
    output wire [287:0] stimulus_stats
);
    localparam integer MS_CYCLES=(PIXEL_HZ/1000 < 1) ? 1 : PIXEL_HZ/1000;
    reg [$clog2(MS_CYCLES+1)-1:0] ms_count;
    wire ms_tick=(ms_count==MS_CYCLES-1);
    reg prev_de, prev_vsync, enabled;
    wire frame_start=in_vsync && !prev_vsync;
    reg [15:0] x,y,hold_ms,gray_ms,state_age,observation_age;
    reg [2:0] smooth_shift;
    reg [31:0] state_word;
    reg [15:0] age[0:4];
    reg [15:0] cur_x0[0:4],cur_y0[0:4],cur_x1[0:4],cur_y1[0:4];
    reg [15:0] dst_x0[0:4],dst_y0[0:4],dst_x1[0:4],dst_y1[0:4];
    reg [23:0] color[0:4];
    reg [4:0] confirmed;
    wire [31:0] cfg [0:31];
    genvar g;
    generate for(g=0;g<32;g=g+1) begin: unpack_config
        assign cfg[g]=settings[g*32+:32];
    end endgenerate
    wire [16:0] expire_ms={1'b0,hold_ms}+{1'b0,gray_ms};
    wire heartbeat_ok=state_age<3000;
    wire current_direction=state_word[6] && observation_age<=250;
    function automatic [15:0] approach(input [15:0] a,b,input [2:0] shift);
        reg [15:0] gap,step;
        begin
            gap=(b>a)?b-a:a-b; step=gap>>shift;
            if(gap!=0 && step==0)step=1;
            approach=(b>a)?a+step:a-step;
        end
    endfunction
    integer i;
    always @(posedge clk) begin
        if(!resetn) begin
            ms_count<=0;prev_de<=0;prev_vsync<=0;x<=0;y<=0;frame_count<=0;
            enabled<=0;hold_ms<=1500;gray_ms<=500;smooth_shift<=2;state_age<=16'hffff;observation_age<=16'hffff;state_word<=0;confirmed<=0;
            for(i=0;i<5;i=i+1) begin
                age[i]<=16'hffff;color[i]<=0;
                cur_x0[i]<=0;cur_y0[i]<=0;cur_x1[i]<=0;cur_y1[i]<=0;
                dst_x0[i]<=0;dst_y0[i]<=0;dst_x1[i]<=0;dst_y1[i]<=0;
            end
        end else begin
            ms_count<=ms_tick?0:ms_count+1'b1;
            prev_de<=in_de;prev_vsync<=in_vsync;
            if(frame_start)begin x<=0;y<=0;frame_count<=frame_count+1'b1;end
            else if(in_de) x<=x+1'b1;
            else if(prev_de)begin x<=0;y<=y+1'b1;end
            if(ms_tick)begin
                if(state_age!=16'hffff)state_age<=state_age+1'b1;
                if(observation_age!=16'hffff)observation_age<=observation_age+1'b1;
                for(i=0;i<5;i=i+1)if(age[i]!=16'hffff)age[i]<=age[i]+1'b1;
            end
            if(frame_start)for(i=0;i<5;i=i+1)begin
                cur_x0[i]<=approach(cur_x0[i],dst_x0[i],smooth_shift);
                cur_y0[i]<=approach(cur_y0[i],dst_y0[i],smooth_shift);
                cur_x1[i]<=approach(cur_x1[i],dst_x1[i],smooth_shift);
                cur_y1[i]<=approach(cur_y1[i],dst_y1[i],smooth_shift);
            end
            // apply is a frame-boundary pulse after the held bus has settled.
            if(apply)begin
                enabled<=cfg[8][0];state_word<=cfg[14];state_age<=0;observation_age<=cfg[10][15:0];
                hold_ms<=cfg[11][15:0]>5000?5000:cfg[11][15:0];
                gray_ms<=cfg[12][15:0]>2000?2000:cfg[12][15:0];
                smooth_shift<=cfg[13][2:0]>4?4:cfg[13][2:0];
                for(i=0;i<5;i=i+1)begin
                    confirmed[i]<=0;
                    if(cfg[8][1])age[i]<=16'hffff;
                    else if(cfg[9][i] && cfg[16+3*i][15:0]<cfg[17+3*i][15:0] &&
                            cfg[16+3*i][31:16]<cfg[17+3*i][31:16] &&
                            cfg[17+3*i][15:0]<=WIDTH && cfg[17+3*i][31:16]<=HEIGHT)begin
                        age[i]<=cfg[10][15:0];confirmed[i]<=1;color[i]<=cfg[18+3*i][23:0];
                        dst_x0[i]<=cfg[16+3*i][15:0];dst_y0[i]<=cfg[16+3*i][31:16];
                        dst_x1[i]<=cfg[17+3*i][15:0];dst_y1[i]<=cfg[17+3*i][31:16];
                        if({1'b0,age[i]}>=expire_ms)begin
                            cur_x0[i]<=cfg[16+3*i][15:0];cur_y0[i]<=cfg[16+3*i][31:16];
                            cur_x1[i]<=cfg[17+3*i][15:0];cur_y1[i]<=cfg[17+3*i][31:16];
                        end
                    end
                end
            end
        end
    end
    reg [23:0] pixel;
    wire [23:0] stimulus_pixel;
    wire [31:0] stim_frames,stim_epoch,stim_ticks,stim_gap;
    wire [127:0] stim_rising;wire stim_active;
    assign stimulus_stats={31'b0,stim_active,stim_rising,stim_gap,stim_ticks,stim_frames,stim_epoch};
    stimulus_core #(.WIDTH(WIDTH),.HEIGHT(HEIGHT)) stimulus(
      .clk(clk),.resetn(resetn),.frame_start(frame_start),.de(in_de),.x(x),.y(y),
      .in_data(pixel),.apply(apply),.enable(cfg[31][0]),.epoch(cfg[15]),
      .pixel(stimulus_pixel),.frames(stim_frames),.applied_epoch(stim_epoch),.active(stim_active),
      .ticks(stim_ticks),.max_gap(stim_gap),.rising_counts(stim_rising));
    integer j,mid_x,mid_y,target_x;
    reg hit;
    always @* begin
        pixel=in_data;hit=0;mid_x=0;mid_y=0;target_x=WIDTH/2;
        if(in_de && enabled)begin
            for(j=0;j<5;j=j+1)begin
                if({1'b0,age[j]}<expire_ms && x>=cur_x0[j] && x<cur_x1[j] && y>=cur_y0[j] && y<cur_y1[j])begin
                    mid_x=(cur_x0[j]+{1'b0,cur_x1[j]})/2;
                    mid_y=(cur_y0[j]+{1'b0,cur_y1[j]})/2;
                    if(j<3)hit=(x-cur_x0[j]<3 || cur_x1[j]-x<=3 || y-cur_y0[j]<3 || cur_y1[j]-y<=3);
                    else hit=(x+1>=mid_x && x<=mid_x+1)||(y+1>=mid_y && y<=mid_y+1);
                    if(hit)pixel=(!confirmed[j] || age[j]>=hold_ms)?24'h808080:color[j];
                end
            end
            // Current status is never inferred from the retained shape colors.
            if(y<24)begin
                pixel=24'h080808;
                if(y>=5 && y<19 && x>=8 && x<WIDTH-8)begin
                    pixel=24'h0050dc;
                    if(heartbeat_ok && (state_word[2:0]==1 || (current_direction && state_word[5:3]==1)) && x<WIDTH/3-8)pixel=24'hd2dc00;
                    if(heartbeat_ok && (state_word[2:0]==2 || (current_direction && state_word[5:3]==2)) && x>=WIDTH/3+8 && x<2*WIDTH/3-8)pixel=24'hd2dc00;
                    if(heartbeat_ok && (state_word[2:0]==3 || (current_direction && state_word[5:3]==3)) && x>=2*WIDTH/3+8)pixel=24'hd2dc00;
                end
                if(y>=21 && heartbeat_ok && x<(WIDTH*state_word[9:7])/3)pixel=24'h00dc00;
            end
            if(heartbeat_ok && state_word[2:0]>=1 && state_word[2:0]<=3)begin
                if(state_word[2:0]==1)target_x=WIDTH*8/100;
                else if(state_word[2:0]==3)target_x=WIDTH*92/100;
                if(x+10>=target_x && x<=target_x+10 && y+10>=HEIGHT*18/100 && y<=HEIGHT*18/100+10)pixel=24'hffffff;
            end
        end
    end
    always @(posedge clk)begin
        if(!resetn)begin
            out_data<=0;out_de<=0;out_hsync<=0;out_vsync<=0;out_hblank<=0;out_vblank<=0;out_field<=0;
        end else begin
            out_data<=stimulus_pixel;out_de<=in_de;out_hsync<=in_hsync;out_vsync<=in_vsync;
            out_hblank<=in_hblank;out_vblank<=in_vblank;out_field<=in_field;
        end
    end
endmodule
