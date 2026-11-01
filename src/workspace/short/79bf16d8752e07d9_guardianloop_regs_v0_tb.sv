`timescale 1 ns / 1 ps

module guardianloop_regs_v0_tb;

    localparam logic [31:0] BUILD_ID_VALUE = 32'h474C_0001;

    logic        s_axi_aclk;
    logic        s_axi_aresetn;
    logic [3:0]  s_axi_awaddr;
    logic [2:0]  s_axi_awprot;
    logic        s_axi_awvalid;
    wire         s_axi_awready;
    logic [31:0] s_axi_wdata;
    logic [3:0]  s_axi_wstrb;
    logic        s_axi_wvalid;
    wire         s_axi_wready;
    wire [1:0]   s_axi_bresp;
    wire         s_axi_bvalid;
    logic        s_axi_bready;
    logic [3:0]  s_axi_araddr;
    logic [2:0]  s_axi_arprot;
    logic        s_axi_arvalid;
    wire         s_axi_arready;
    wire [31:0]  s_axi_rdata;
    wire [1:0]   s_axi_rresp;
    wire         s_axi_rvalid;
    logic        s_axi_rready;
    integer      error_count;

    guardianloop_regs_v0_v1_0 dut (
        .s_axi_aclk(s_axi_aclk),
        .s_axi_aresetn(s_axi_aresetn),
        .s_axi_awaddr(s_axi_awaddr),
        .s_axi_awprot(s_axi_awprot),
        .s_axi_awvalid(s_axi_awvalid),
        .s_axi_awready(s_axi_awready),
        .s_axi_wdata(s_axi_wdata),
        .s_axi_wstrb(s_axi_wstrb),
        .s_axi_wvalid(s_axi_wvalid),
        .s_axi_wready(s_axi_wready),
        .s_axi_bresp(s_axi_bresp),
        .s_axi_bvalid(s_axi_bvalid),
        .s_axi_bready(s_axi_bready),
        .s_axi_araddr(s_axi_araddr),
        .s_axi_arprot(s_axi_arprot),
        .s_axi_arvalid(s_axi_arvalid),
        .s_axi_arready(s_axi_arready),
        .s_axi_rdata(s_axi_rdata),
        .s_axi_rresp(s_axi_rresp),
        .s_axi_rvalid(s_axi_rvalid),
        .s_axi_rready(s_axi_rready)
    );

    always #5 s_axi_aclk = ~s_axi_aclk;

    task automatic expect_equal(
        input logic [31:0] actual,
        input logic [31:0] expected,
        input string label
    );
        begin
            if (actual !== expected) begin
                error_count = error_count + 1;
                $display("FAIL: %s expected=%08h actual=%08h", label, expected, actual);
            end else begin
                $display("PASS: %s value=%08h", label, actual);
            end
        end
    endtask

    task automatic axi_write(
        input logic [3:0] addr,
        input logic [31:0] data,
        input logic [3:0] strb
    );
        begin
            @(negedge s_axi_aclk);
            s_axi_awaddr  = addr;
            s_axi_awvalid = 1'b1;
            s_axi_wdata   = data;
            s_axi_wstrb   = strb;
            s_axi_wvalid  = 1'b1;

            while (!(s_axi_awvalid && s_axi_awready && s_axi_wvalid && s_axi_wready)) begin
                @(posedge s_axi_aclk);
            end

            @(negedge s_axi_aclk);
            s_axi_awvalid = 1'b0;
            s_axi_wvalid  = 1'b0;
            s_axi_bready  = 1'b1;

            while (!s_axi_bvalid) begin
                @(posedge s_axi_aclk);
            end
            if (s_axi_bresp !== 2'b00) begin
                error_count = error_count + 1;
                $display("FAIL: write response at %0h was %0b", addr, s_axi_bresp);
            end

            @(negedge s_axi_aclk);
            s_axi_bready = 1'b0;
        end
    endtask

    task automatic axi_read(
        input logic [3:0] addr,
        output logic [31:0] data
    );
        begin
            @(negedge s_axi_aclk);
            s_axi_araddr  = addr;
            s_axi_arvalid = 1'b1;

            while (!(s_axi_arvalid && s_axi_arready)) begin
                @(posedge s_axi_aclk);
            end

            @(negedge s_axi_aclk);
            s_axi_arvalid = 1'b0;
            s_axi_rready  = 1'b1;

            while (!s_axi_rvalid) begin
                @(posedge s_axi_aclk);
            end
            data = s_axi_rdata;
            if (s_axi_rresp !== 2'b00) begin
                error_count = error_count + 1;
                $display("FAIL: read response at %0h was %0b", addr, s_axi_rresp);
            end

            @(negedge s_axi_aclk);
            s_axi_rready = 1'b0;
        end
    endtask

    logic [31:0] read_data;

    initial begin
        s_axi_aclk    = 1'b0;
        s_axi_aresetn = 1'b0;
        s_axi_awaddr  = '0;
        s_axi_awprot  = '0;
        s_axi_awvalid = 1'b0;
        s_axi_wdata   = '0;
        s_axi_wstrb   = '0;
        s_axi_wvalid  = 1'b0;
        s_axi_bready  = 1'b0;
        s_axi_araddr  = '0;
        s_axi_arprot  = '0;
        s_axi_arvalid = 1'b0;
        s_axi_rready  = 1'b0;
        error_count   = 0;

        repeat (5) @(posedge s_axi_aclk);
        s_axi_aresetn = 1'b1;
        repeat (2) @(posedge s_axi_aclk);

        axi_read(4'h0, read_data);
        expect_equal(read_data, 32'h0000_0000, "SCRATCH reset");
        axi_read(4'h4, read_data);
        expect_equal(read_data, BUILD_ID_VALUE, "BUILD_ID reset");
        axi_read(4'h8, read_data);
        expect_equal(read_data, 32'h0000_0001, "STATUS after reset release");

        axi_write(4'h0, 32'hA5A5_5A5A, 4'hF);
        axi_read(4'h0, read_data);
        expect_equal(read_data, 32'hA5A5_5A5A, "SCRATCH first full write");

        axi_write(4'h0, 32'h1234_5678, 4'hF);
        axi_read(4'h0, read_data);
        expect_equal(read_data, 32'h1234_5678, "SCRATCH second full write");

        axi_write(4'h0, 32'hDEAD_BEEF, 4'h3);
        axi_read(4'h0, read_data);
        expect_equal(read_data, 32'h1234_BEEF, "SCRATCH WSTRB write");

        axi_write(4'h4, 32'hFFFF_FFFF, 4'hF);
        axi_read(4'h4, read_data);
        expect_equal(read_data, BUILD_ID_VALUE, "BUILD_ID write ignored");

        axi_write(4'h8, 32'hFFFF_FFFF, 4'hF);
        axi_read(4'h8, read_data);
        expect_equal(read_data, 32'h0000_0001, "STATUS write ignored");

        axi_write(4'hC, 32'hCAFEBABE, 4'hF);
        axi_read(4'hC, read_data);
        expect_equal(read_data, 32'h0000_0000, "undefined address read zero");

        if (error_count == 0) begin
            $display("AXI-Lite v0 simulation PASSED");
            $finish;
        end else begin
            $display("AXI-Lite v0 simulation FAILED with %0d errors", error_count);
            $fatal(1);
        end
    end

endmodule
