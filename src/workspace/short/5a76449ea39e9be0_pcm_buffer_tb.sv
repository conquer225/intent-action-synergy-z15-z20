`timescale 1ns/1ps
module pcm_buffer_tb #(parameter USE_TICKS=0, DEPTH=32);
    reg clk=0, sample_clk=0;
    always #5 clk=~clk;
    always #503 sample_clk=~sample_clk;
    reg rstn=0;
    reg [5:0] awaddr=0, araddr=0;
    reg awvalid=0, wvalid=0, bready=0, arvalid=0, rready=0;
    wire awready,wready,bvalid,arready,rvalid;
    reg [31:0] wdata=0;
    reg [3:0] wstrb=15;
    wire [31:0] rdata;
    wire [1:0] bresp,rresp;
    wire [15:0] left,right;
    reg [1:0] divider=0;
    always @(negedge sample_clk) divider <= divider + 1'b1;
    wire sample_enable=!USE_TICKS || divider==3;
    pcm_buffer #(.FIFO_DEPTH(DEPTH), .USE_SAMPLE_ENABLE(USE_TICKS)) dut(
        .s_axi_aclk(clk),.s_axi_aresetn(rstn),
        .s_axi_awaddr(awaddr),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
        .s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
        .s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),
        .s_axi_araddr(araddr),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
        .s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready),
        .sample_clk(sample_clk),.sample_enable(sample_enable),.sample_left(left),.sample_right(right));
    task automatic write_reg(input [5:0] addr,input [31:0] value,input bit data_first,input [1:0] expected);
        @(negedge clk);
        if (data_first) begin
            wdata=value;wvalid=1;
            do @(posedge clk); while (!wready);
            @(negedge clk);wvalid=0;
            repeat(3) @(negedge clk);
            awaddr=addr;awvalid=1;
            do @(posedge clk); while (!awready);
            @(negedge clk);awvalid=0;
        end else begin
            awaddr=addr;awvalid=1;
            do @(posedge clk); while (!awready);
            @(negedge clk);awvalid=0;
            repeat(2) @(negedge clk);
            wdata=value;wvalid=1;
            do @(posedge clk); while (!wready);
            @(negedge clk);wvalid=0;
        end
        wait(bvalid);#1;
        if (bresp!==expected) $fatal(1,"write response addr=%h actual=%b expected=%b full=%b busy=%b held=%b count=%d",addr,bresp,expected,dut.full,dut.wr_busy,dut.held_reset,dut.queued);
        repeat(3) begin @(posedge clk);#1;if (!bvalid||bresp!==expected) $fatal(1,"B not stable");end
        @(negedge clk);bready=1;@(negedge clk);bready=0;
    endtask
    task automatic read_reg(input [5:0] addr,output [31:0] value);
        @(negedge clk);araddr=addr;arvalid=1;
        do @(posedge clk); while (!arready);
        @(negedge clk);arvalid=0;
        wait(rvalid);#1;value=rdata;
        repeat(3) begin @(posedge clk);#1;if (!rvalid||rdata!==value) $fatal(1,"R not stable");end
        @(negedge clk);rready=1;@(negedge clk);rready=0;
    endtask
    integer got=0;
    bit check_order=0;
    always @(posedge sample_clk) begin
        if (check_order && (left!=0 || right!=0)) begin
            if (left!==16'(got+1) || right!==16'(16'h8000+got+1))
                $fatal(1,"sample mismatch index=%d L=%h R=%h",got,left,right);
            got=got+1;
        end
    end
    reg [31:0] value;
    initial begin
        #100;rstn=1;
        repeat(12) @(posedge sample_clk);
        read_reg(0,value);if(value!==32'h474c4101)$fatal(1,"ID");
        write_reg(4,0,0,0);
        wait(!dut.wr_busy && !dut.rd_busy);
        repeat(3) @(posedge sample_clk);
        for(integer n=0;n<DEPTH-1;n=n+1) write_reg(16,{16'(16'h8001+n),16'(n+1)},n%2,0);
        repeat(10) @(posedge clk);
        read_reg(8,value);if(value!==DEPTH-1)$fatal(1,"queue=%d",value);
        write_reg(16,32'hffffeeee,0,2);
        wstrb=3;write_reg(16,32'h11112222,1,2);wstrb=15;
        check_order=1;write_reg(4,1,0,0);
        wait(got==DEPTH-1);repeat(12) @(posedge sample_clk);#1;
        if(left!==0||right!==0)$fatal(1,"underrun must be silence");
        read_reg(20,value);if(value<2)$fatal(1,"missing underruns");
        check_order=0;
        write_reg(4,2,1,0);repeat(12) @(posedge sample_clk);
        if(left!==0||right!==0)$fatal(1,"held reset silence");
        write_reg(16,32'h11112222,0,2);
        write_reg(4,0,0,0);wait(!dut.wr_busy && !dut.rd_busy);repeat(3) @(posedge sample_clk);
        read_reg(8,value);if(value!==0)$fatal(1,"flush failed");
        write_reg(16,32'h22221111,1,0);
        write_reg(4,1,0,0);
        wait(left!=0 || right!=0);
        write_reg(4,2,0,0);
        #1;if(left!==0||right!==0)$fatal(1,"software reset leaked active audio");
        repeat(12) @(posedge sample_clk);
        write_reg(4,0,0,0);wait(!dut.wr_busy && !dut.rd_busy);
        write_reg(16,32'h22221111,1,0);
        write_reg(4,1,0,0);
        wait(left!=0 || right!=0);
        #17;rstn=0;#1;if(left!==0||right!==0)$fatal(1,"reset leaked active audio");
        repeat(12) @(posedge sample_clk);rstn=1;
        repeat(10) @(posedge sample_clk);
        read_reg(4,value);if(value!==2)$fatal(1,"must reset disabled");
        $display("PCM_BUFFER_PASS order=%0d use_ticks=%0d overflow=PASS split_axi=PASS response_backpressure=PASS flush=PASS reset=PASS underrun_silence=PASS",got,USE_TICKS);
        $finish;
    end
    initial begin #(DEPTH*10000);$fatal(1,"timeout");end
endmodule

module pcm_ticks_tb;
    pcm_buffer_tb #(.USE_TICKS(1)) test();
endmodule

module pcm_capacity_tb;
    pcm_buffer_tb #(.USE_TICKS(1), .DEPTH(8192)) test();
endmodule
