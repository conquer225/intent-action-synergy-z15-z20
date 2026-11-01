`timescale 1 ns / 1 ps

module guardianloop_regs_v0_v1_0_S_AXI #(
    parameter integer C_S_AXI_DATA_WIDTH = 32,
    parameter integer C_S_AXI_ADDR_WIDTH = 4
) (
    input  wire                              s_axi_aclk,
    input  wire                              s_axi_aresetn,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0]     s_axi_awaddr,
    input  wire [2:0]                        s_axi_awprot,
    input  wire                              s_axi_awvalid,
    output wire                              s_axi_awready,
    input  wire [C_S_AXI_DATA_WIDTH-1:0]     s_axi_wdata,
    input  wire [(C_S_AXI_DATA_WIDTH/8)-1:0] s_axi_wstrb,
    input  wire                              s_axi_wvalid,
    output wire                              s_axi_wready,
    output wire [1:0]                        s_axi_bresp,
    output wire                              s_axi_bvalid,
    input  wire                              s_axi_bready,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0]     s_axi_araddr,
    input  wire [2:0]                        s_axi_arprot,
    input  wire                              s_axi_arvalid,
    output wire                              s_axi_arready,
    output wire [C_S_AXI_DATA_WIDTH-1:0]     s_axi_rdata,
    output wire [1:0]                        s_axi_rresp,
    output wire                              s_axi_rvalid,
    input  wire                              s_axi_rready
);

    localparam integer ADDR_LSB = (C_S_AXI_DATA_WIDTH / 32) + 1;
    localparam [C_S_AXI_DATA_WIDTH-1:0] BUILD_ID_VALUE = 32'h474C_0001;

    reg [C_S_AXI_ADDR_WIDTH-1:0] awaddr_reg;
    reg                           awaddr_valid_reg;
    reg [C_S_AXI_DATA_WIDTH-1:0] wdata_reg;
    reg [(C_S_AXI_DATA_WIDTH/8)-1:0] wstrb_reg;
    reg                           wdata_valid_reg;
    reg                           bvalid_reg;
    reg [C_S_AXI_DATA_WIDTH-1:0] scratch_reg;
    reg                           rvalid_reg;
    reg [C_S_AXI_DATA_WIDTH-1:0] rdata_reg;
    integer                       byte_index;

    assign s_axi_awready = s_axi_aresetn && !awaddr_valid_reg && !bvalid_reg;
    assign s_axi_wready  = s_axi_aresetn && !wdata_valid_reg && !bvalid_reg;
    assign s_axi_bvalid  = bvalid_reg;
    assign s_axi_bresp   = 2'b00;

    assign s_axi_arready = s_axi_aresetn && !rvalid_reg;
    assign s_axi_rvalid  = rvalid_reg;
    assign s_axi_rresp   = 2'b00;
    assign s_axi_rdata   = rdata_reg;

    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            awaddr_reg      <= {C_S_AXI_ADDR_WIDTH{1'b0}};
            awaddr_valid_reg <= 1'b0;
            wdata_reg       <= {C_S_AXI_DATA_WIDTH{1'b0}};
            wstrb_reg       <= {(C_S_AXI_DATA_WIDTH/8){1'b0}};
            wdata_valid_reg <= 1'b0;
            bvalid_reg      <= 1'b0;
            scratch_reg     <= {C_S_AXI_DATA_WIDTH{1'b0}};
        end else begin
            if (s_axi_awvalid && s_axi_awready) begin
                awaddr_reg       <= s_axi_awaddr;
                awaddr_valid_reg <= 1'b1;
            end

            if (s_axi_wvalid && s_axi_wready) begin
                wdata_reg       <= s_axi_wdata;
                wstrb_reg       <= s_axi_wstrb;
                wdata_valid_reg <= 1'b1;
            end

            if (awaddr_valid_reg && wdata_valid_reg && !bvalid_reg) begin
                if (awaddr_reg[ADDR_LSB+1:ADDR_LSB] == 2'b00) begin
                    for (byte_index = 0; byte_index < (C_S_AXI_DATA_WIDTH/8); byte_index = byte_index + 1) begin
                        if (wstrb_reg[byte_index]) begin
                            scratch_reg[byte_index*8 +: 8] <= wdata_reg[byte_index*8 +: 8];
                        end
                    end
                end

                awaddr_valid_reg <= 1'b0;
                wdata_valid_reg  <= 1'b0;
                bvalid_reg       <= 1'b1;
            end else if (bvalid_reg && s_axi_bready) begin
                bvalid_reg <= 1'b0;
            end
        end
    end

    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            rvalid_reg <= 1'b0;
            rdata_reg  <= {C_S_AXI_DATA_WIDTH{1'b0}};
        end else begin
            if (s_axi_arvalid && s_axi_arready) begin
                rvalid_reg <= 1'b1;
                case (s_axi_araddr[ADDR_LSB+1:ADDR_LSB])
                    2'b00: rdata_reg <= scratch_reg;
                    2'b01: rdata_reg <= BUILD_ID_VALUE;
                    2'b10: rdata_reg <= {{(C_S_AXI_DATA_WIDTH-1){1'b0}}, s_axi_aresetn};
                    default: rdata_reg <= {C_S_AXI_DATA_WIDTH{1'b0}};
                endcase
            end else if (rvalid_reg && s_axi_rready) begin
                rvalid_reg <= 1'b0;
            end
        end
    end

endmodule
