`timescale 1ns/1ps
module primary_filter_top_tb;
    reg aclk=0, aresetn=0;
    always #10 aclk=~aclk; // Candidate PS FCLK0 is 50 MHz; simulation is not timing closure.
    reg [31:0] control_word=1;
    wire [31:0] status_word;
    reg [63:0] s_axis_tdata=0;
    reg [7:0] s_axis_tkeep=8'hff;
    reg s_axis_tlast=0,s_axis_tvalid=0,m_axis_tready=0;
    wire s_axis_tready,m_axis_tlast,m_axis_tvalid;
    wire [63:0] m_axis_tdata;
    wire [7:0] m_axis_tkeep;
    primary_filter_top dut(.*);
    integer fd,rc,r,ch,j,n=0,waited;
    reg [39:0] value,expected;
    task soft_reset;
        begin
            @(negedge aclk); control_word=1;s_axis_tvalid=0;m_axis_tready=0;
            repeat (3) @(negedge aclk);
            if (status_word!==32'h50460001 || s_axis_tready || m_axis_tvalid)
                $fatal(1,"Reset/status ABI mismatch");
            control_word=0;
            @(negedge aclk);
            if (status_word!==32'h50460000) $fatal(1,"Release/status ABI mismatch");
        end
    endtask
    task first_frame;
        begin
            fd=$fopen("vectors.txt","r");
            if (!fd) $fatal(1,"Missing golden vectors");
            for (j=0;j<80;j=j+1) begin
                rc=$fscanf(fd,"%d %d %h %h\n",r,ch,value,expected);
                if (rc!=4 || ch!=j%8) $fatal(1,"Invalid vector");
                while (!s_axis_tready) @(negedge aclk);
                s_axis_tdata={{24{value[39]}},value};s_axis_tlast=j==79;s_axis_tvalid=1;
                @(negedge aclk);s_axis_tvalid=0;
                waited=0;
                while (!m_axis_tvalid) begin
                    @(negedge aclk);waited=waited+1;
                    if (waited>32) $fatal(1,"Result timeout");
                end
                repeat (2) begin
                    if (m_axis_tdata!=={{24{expected[39]}},expected} || m_axis_tlast!==(j==79) ||
                        m_axis_tkeep!==8'hff || status_word!==32'h50460000 || !m_axis_tvalid)
                        $fatal(1,"Top-level data/status mismatch");
                    @(negedge aclk);
                end
                m_axis_tready=1;@(negedge aclk);m_axis_tready=0;
                n=n+1;
            end
            $fclose(fd);
        end
    endtask
    initial begin
        repeat (3) @(negedge aclk);
        if (status_word!==32'h50460001) $fatal(1,"Power reset missing");
        aresetn=1;
        soft_reset();first_frame();
        // Inject an early TLAST after a complete frame.
        s_axis_tlast=1;s_axis_tvalid=1;
        @(negedge aclk);s_axis_tvalid=0;
        repeat (35) begin
            @(negedge aclk);
            if (status_word!==32'h50460002 || s_axis_tready || m_axis_tvalid)
                $fatal(1,"Sticky fault status missing");
        end
        soft_reset();first_frame();
        // Reset while a word is still in flight, then verify no stale output.
        s_axis_tlast=0;s_axis_tvalid=1;
        @(negedge aclk);s_axis_tvalid=0;
        repeat (4) @(negedge aclk);
        soft_reset();
        repeat (32) begin
            @(negedge aclk);
            if (m_axis_tvalid) $fatal(1,"Stale result after software reset");
        end
        aresetn=0;repeat (3) @(negedge aclk);
        if (status_word!==32'h50460001) $fatal(1,"External reset missing");
        $display("CONTROL_PASS words=%0d frames=2 reset_abort=PASS fault_status=PASS recovery=PASS",n);
        $finish;
    end
    initial begin #1000000;$fatal(1,"Test timeout");end
endmodule
