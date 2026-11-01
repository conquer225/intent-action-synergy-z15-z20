`timescale 1ns/1ps
module primary_sos_axis_tb;
    reg aclk=0, areset=1;
    always #5 aclk=~aclk;
    reg [63:0] s_axis_tdata=0;
    reg [7:0] s_axis_tkeep=8'hff;
    reg s_axis_tlast=0,s_axis_tvalid=0,m_axis_tready=0;
    wire s_axis_tready,m_axis_tlast,m_axis_tvalid,fault;
    wire [63:0] m_axis_tdata;
    wire [7:0] m_axis_tkeep;
    primary_sos_axis dut(.*);
    integer fd,rc,reset_flag,ch,n=0,frame_word=0,j,waited,which,frames=0;
    reg [39:0] value,expected;
    reg expected_last;
    task reset_axis;
        begin
            @(negedge aclk); areset=1;s_axis_tvalid=0;m_axis_tready=0;
            repeat (2) @(negedge aclk);
            if (fault || m_axis_tvalid) $fatal(1,"AXIS reset failure");
            areset=0; frame_word=0;
        end
    endtask
    task expect_closed_fault;
        begin
            @(negedge aclk); s_axis_tvalid=0;
            repeat (35) begin
                @(negedge aclk);
                if (!fault || s_axis_tready || m_axis_tvalid)
                    $fatal(1,"Malformed frame did not stay closed");
            end
        end
    endtask
    initial begin
        reset_axis();
        // Early TLAST, partial TKEEP, bad sign extension, then a missing TLAST.
        for (which=0;which<4;which=which+1) begin
            reset_axis();
            if (which==3) begin
                for (j=0;j<79;j=j+1) begin
                    while (!s_axis_tready) @(negedge aclk);
                    s_axis_tdata=0;s_axis_tkeep=8'hff;s_axis_tlast=0;s_axis_tvalid=1;
                    m_axis_tready=1;
                    @(negedge aclk);s_axis_tvalid=0;
                    while (!m_axis_tvalid) @(negedge aclk);
                    @(negedge aclk);
                end
            end
            while (!s_axis_tready) @(negedge aclk);
            s_axis_tdata=which==2 ? 64'h10000000000 : 0;
            s_axis_tkeep=which==1 ? 8'h0f : 8'hff;
            s_axis_tlast=which==0;
            s_axis_tvalid=1;m_axis_tready=0;
            expect_closed_fault();
        end
        reset_axis();
        // Reset while a valid word is still being processed.
        s_axis_tdata=100;s_axis_tkeep=8'hff;s_axis_tlast=0;s_axis_tvalid=1;
        @(negedge aclk); s_axis_tvalid=0;
        repeat (4) @(negedge aclk);
        reset_axis();
        repeat (30) begin
            @(negedge aclk);
            if (m_axis_tvalid) $fatal(1,"Stale AXIS result after reset");
        end
        fd=$fopen("axis_vectors.txt","r");
        if (!fd) $fatal(1,"Missing AXIS vectors");
        while (!$feof(fd)) begin
            rc=$fscanf(fd,"%d %d %h %h\n",reset_flag,ch,value,expected);
            if (rc!=4) $fatal(1,"Bad AXIS vector");
            if (reset_flag) reset_axis();
            if (ch != frame_word%8) $fatal(1,"Bad channel sequence in test");
            expected_last=frame_word==79;
            repeat (n%3) @(negedge aclk);
            while (!s_axis_tready) @(negedge aclk);
            s_axis_tdata={{24{value[39]}},value};s_axis_tkeep=8'hff;
            s_axis_tlast=expected_last;s_axis_tvalid=1;m_axis_tready=0;
            @(negedge aclk);s_axis_tvalid=0;
            waited=0;
            while (!m_axis_tvalid) begin
                @(negedge aclk);waited=waited+1;
                if (waited>30 || fault) $fatal(1,"AXIS output timeout/fault");
            end
            for (j=0;j<=n%5;j=j+1) begin
                if (m_axis_tdata !== {{24{expected[39]}},expected} || m_axis_tkeep!==8'hff ||
                    m_axis_tlast!==expected_last || !m_axis_tvalid || fault)
                    $fatal(1,"AXIS mismatch/backpressure word %0d",n);
                @(negedge aclk);
            end
            m_axis_tready=1;
            @(negedge aclk);m_axis_tready=0;
            if (expected_last) frames=frames+1;
            frame_word=expected_last ? 0 : frame_word+1;
            n=n+1;
        end
        if (frame_word!=0) $fatal(1,"Incomplete final frame");
        $fclose(fd);
        reset_axis();
        // Numerical overflow must also close the DMA stream, not emit clipped data as valid.
        j=0;
        while (!fault && j<384) begin
            while (!s_axis_tready && !fault) @(negedge aclk);
            case ((j/8)%3)
                0: value=0;
                1: value=40'h7fffffffff;
                2: value=40'h8000000000;
            endcase
            s_axis_tdata={{24{value[39]}},value};s_axis_tlast=(j%80)==79;
            s_axis_tvalid=1;m_axis_tready=0;
            @(negedge aclk);s_axis_tvalid=0;
            waited=0;
            while (!m_axis_tvalid && !fault) begin
                @(negedge aclk);waited=waited+1;
                if (waited>30) $fatal(1,"Overflow test timeout");
            end
            if (!fault) begin
                m_axis_tready=1;
                @(negedge aclk);m_axis_tready=0;
            end
            j=j+1;
        end
        if (!fault) $fatal(1,"No AXIS numerical overflow fault");
        expect_closed_fault();
        reset_axis();
        $display("AXIS_PASS words=%0d frames=%0d malformed=4 reset_abort=PASS backpressure=PASS overflow=PASS",n,frames);
        $finish;
    end
    initial begin #500000000; $fatal(1,"AXIS global timeout"); end
endmodule
