`timescale 1ns/1ps
// One 32-bit word holds signed PCM16 left (15:0), right (31:16).
module pcm_buffer #(
    parameter integer FIFO_DEPTH = 8192,
    parameter integer COUNT_WIDTH = $clog2(FIFO_DEPTH) + 1,
    parameter integer USE_SAMPLE_ENABLE = 0
)(
    input wire s_axi_aclk,
    input wire s_axi_aresetn,
    input wire [5:0] s_axi_awaddr,
    input wire s_axi_awvalid,
    output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,
    input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,
    output wire s_axi_wready,
    output reg [1:0] s_axi_bresp,
    output reg s_axi_bvalid,
    input wire s_axi_bready,
    input wire [5:0] s_axi_araddr,
    input wire s_axi_arvalid,
    output wire s_axi_arready,
    output reg [31:0] s_axi_rdata,
    output reg [1:0] s_axi_rresp,
    output reg s_axi_rvalid,
    input wire s_axi_rready,
    input wire sample_clk,
    input wire sample_enable,
    output wire [15:0] sample_left,
    output wire [15:0] sample_right
);
    reg aw_pending, w_pending;
    reg [5:0] awaddr;
    reg [31:0] wdata;
    reg [3:0] wstrb;
    reg enabled, held_reset;
    wire full, empty, wr_busy, rd_busy;
    wire [31:0] head;
    wire [COUNT_WIDTH-1:0] queued;
    // XPM FWFT capacity differs with the depth/implementation. Expose and
    // enforce one conservative public capacity for every implementation.
    wire at_capacity = full || queued >= FIFO_DEPTH - 1;
    wire fifo_reset = !s_axi_aresetn || held_reset;
    reg push;
    reg [31:0] push_word;
    (* ASYNC_REG = "TRUE" *) reg [1:0] run_sync;
    always @(posedge sample_clk or posedge fifo_reset) begin
        if (fifo_reset) run_sync <= 0;
        else run_sync <= {run_sync[0], enabled};
    end
    // run_sync clears asynchronously; keep host-domain reset out of FIFO rd_en.
    wire playing = run_sync[1] && !rd_busy;
    wire sample_tick = !USE_SAMPLE_ENABLE || sample_enable;
    wire pop = playing && !empty && sample_tick;
    assign sample_left = pop ? head[15:0] : 16'd0;
    assign sample_right = pop ? head[31:16] : 16'd0;

    xpm_fifo_async #(
        .FIFO_MEMORY_TYPE("block"), .ECC_MODE("no_ecc"),
        .RELATED_CLOCKS(0), .FIFO_WRITE_DEPTH(FIFO_DEPTH),
        .WRITE_DATA_WIDTH(32), .READ_DATA_WIDTH(32),
        .WR_DATA_COUNT_WIDTH(COUNT_WIDTH), .RD_DATA_COUNT_WIDTH(COUNT_WIDTH),
        .READ_MODE("fwft"), .FIFO_READ_LATENCY(0), .CDC_SYNC_STAGES(2),
        .USE_ADV_FEATURES("0707"), .DOUT_RESET_VALUE("0"),
        .PROG_FULL_THRESH(10), .PROG_EMPTY_THRESH(10), .SIM_ASSERT_CHK(1)
    ) fifo (
        .rst(fifo_reset), .wr_clk(s_axi_aclk), .wr_en(push && s_axi_aresetn && !held_reset), .din(push_word),
        .full(full), .wr_rst_busy(wr_busy), .wr_data_count(queued),
        .rd_clk(sample_clk), .rd_en(pop), .dout(head), .empty(empty),
        .rd_rst_busy(rd_busy), .sleep(1'b0),
        .injectsbiterr(1'b0), .injectdbiterr(1'b0),
        .almost_empty(), .almost_full(), .data_valid(), .dbiterr(), .sbiterr(),
        .overflow(), .underflow(), .prog_empty(), .prog_full(),
        .rd_data_count(), .wr_ack()
    );
    reg [31:0] underruns, underruns_gray;
    always @(posedge sample_clk or posedge fifo_reset) begin
        if (fifo_reset) begin underruns <= 0; underruns_gray <= 0; end
        else if (playing && empty && sample_tick) begin
            underruns <= underruns + 1;
            underruns_gray <= ((underruns + 1) >> 1) ^ (underruns + 1);
        end
    end
    (* ASYNC_REG = "TRUE" *) reg [31:0] gray_sync0, gray_sync1;
    integer i;
    reg [31:0] underruns_host;
    always @* begin
        underruns_host[31] = gray_sync1[31];
        for (i=30; i>=0; i=i-1) underruns_host[i] = underruns_host[i+1] ^ gray_sync1[i];
    end
    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin gray_sync0 <= 0; gray_sync1 <= 0; end
        else begin gray_sync0 <= underruns_gray; gray_sync1 <= gray_sync0; end
    end
    assign s_axi_awready = !aw_pending && !s_axi_bvalid;
    assign s_axi_wready = !w_pending && !s_axi_bvalid;
    assign s_axi_arready = !s_axi_rvalid;
    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            aw_pending <= 0; w_pending <= 0; awaddr <= 0; wdata <= 0; wstrb <= 0;
            s_axi_bvalid <= 0; s_axi_bresp <= 0;
            s_axi_rvalid <= 0; s_axi_rresp <= 0; s_axi_rdata <= 0;
            enabled <= 0; held_reset <= 1; push <= 0; push_word <= 0;
        end else begin
            push <= 0;
            if (s_axi_awready && s_axi_awvalid) begin aw_pending <= 1; awaddr <= s_axi_awaddr; end
            if (s_axi_wready && s_axi_wvalid) begin w_pending <= 1; wdata <= s_axi_wdata; wstrb <= s_axi_wstrb; end
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 0;
            if (aw_pending && w_pending && !s_axi_bvalid) begin
                aw_pending <= 0; w_pending <= 0;
                s_axi_bvalid <= 1; s_axi_bresp <= 0;
                case (awaddr)
                    6'h04: begin
                        if (!wstrb[0] || wdata[31:2]!=0 || wdata[1:0]==3)
                            s_axi_bresp <= 2'b10;
                        else begin enabled <= wdata[0]; held_reset <= wdata[1]; end
                    end
                    6'h10: begin
                        if (wstrb!=4'b1111 || held_reset || wr_busy || at_capacity)
                            s_axi_bresp <= 2'b10;
                        else begin push <= 1; push_word <= wdata; end
                    end
                    default: s_axi_bresp <= 2'b10;
                endcase
            end
            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 0;
            if (s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid <= 1; s_axi_rresp <= 0;
                case (s_axi_araddr)
                    6'h00: s_axi_rdata <= 32'h474c4101;
                    6'h04: s_axi_rdata <= {30'd0,held_reset,enabled};
                    6'h08: s_axi_rdata <= {{(32-COUNT_WIDTH){1'b0}},queued};
                    6'h0c: s_axi_rdata <= {29'd0,wr_busy,at_capacity,held_reset};
                    6'h14: s_axi_rdata <= underruns_host;
                    6'h18: s_axi_rdata <= FIFO_DEPTH - 1;
                    6'h1c: s_axi_rdata <= 48000;
                    default: begin s_axi_rdata <= 0; s_axi_rresp <= 2'b10; end
                endcase
            end
        end
    end
endmodule
