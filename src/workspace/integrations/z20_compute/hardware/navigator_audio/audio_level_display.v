// Simple HDMI level view; video timing is owned by video_driver.
module audio_level_display(
    input pixel_clk,
    input rst_n,
    input [10:0] pixel_xpos,
    input [10:0] pixel_ypos,
    input [7:0] level,
    output reg [23:0] pixel_data
);
    wire [10:0] bar_end = 11'd100 + {level, 2'b00};
    always @(posedge pixel_clk or negedge rst_n) begin
        if (!rst_n)
            pixel_data <= 24'h000000;
        else if (pixel_ypos >= 11'd580 && pixel_ypos < 11'd640 &&
                 pixel_xpos >= 11'd100 && pixel_xpos < bar_end)
            pixel_data <= 24'h44DDAA;
        else if ((pixel_ypos == 11'd579 || pixel_ypos == 11'd640) &&
                 pixel_xpos >= 11'd100 && pixel_xpos < 11'd1124)
            pixel_data <= 24'hCCCCCC;
        else if (pixel_xpos >= 11'd100 && pixel_xpos < 11'd1124 &&
                 pixel_ypos >= 11'd160 && pixel_ypos < 11'd164)
            pixel_data <= 24'h555555;
        else
            pixel_data <= 24'h101820;
    end
endmodule
