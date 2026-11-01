`timescale 1ns/1ps
// AXIS filter-side regression. This does not instantiate the AXI DMA IP.
module inflight_stream_reset_tb;
    reg aclk=0, aresetn=0;
    always #10 aclk=~aclk;
    reg [31:0] control_word=1;
    wire [31:0] status_word;
    reg [63:0] s_axis_tdata=0;
    reg [7:0] s_axis_tkeep=8'hff;
    reg s_axis_tlast=0, s_axis_tvalid=0, m_axis_tready=0;
    wire s_axis_tready, m_axis_tlast, m_axis_tvalid;
    wire [63:0] m_axis_tdata;
    wire [7:0] m_axis_tkeep;
    primary_filter_top dut(.*);
    reg [39:0] value[0:79], expected[0:79];
    integer fd, scanned, reset_flag, ch, i, scenario, waited;

    task send_input(input integer index, input reg last);
        begin
            @(negedge aclk);
            while (!s_axis_tready) @(negedge aclk);
            s_axis_tdata={{24{value[index][39]}},value[index]};
            s_axis_tlast=last;
            s_axis_tvalid=1;
            @(negedge aclk);
            s_axis_tvalid=0;
        end
    endtask

    task expect_output(input integer index, input reg last);
        begin
            waited=0;
            while (!m_axis_tvalid) begin
                @(negedge aclk);
                waited=waited+1;
                if (waited>60 || status_word!==32'h50460000)
                    $fatal(1,"No good output for index %0d",index);
            end
            if (m_axis_tdata!=={{24{expected[index][39]}},expected[index]} ||
                m_axis_tkeep!==8'hff || m_axis_tlast!==last)
                $fatal(1,"Old/incorrect data after reset, index %0d",index);
            m_axis_tready=1;
            @(negedge aclk);
            m_axis_tready=0;
        end
    endtask

    initial begin
        fd=$fopen("vectors.txt","r");
        if (!fd) $fatal(1,"Missing previously audited vectors");
        for (i=0;i<80;i=i+1) begin
            scanned=$fscanf(fd,"%d %d %h %h\n",reset_flag,ch,value[i],expected[i]);
            if (scanned!=4 || ch!=i%8 || reset_flag!==(i==0))
                $fatal(1,"Unexpected golden vector %0d",i);
        end
        $fclose(fd);
        repeat (20) @(negedge aclk);
        aresetn=1; control_word=0;
        repeat (3) @(negedge aclk);
        for (scenario=0;scenario<2;scenario=scenario+1) begin
            if (scenario==1) begin
                control_word=1;
                repeat (20) @(negedge aclk);
                control_word=0;
                repeat (3) @(negedge aclk);
            end
            // A DMA-sized frame has already yielded a partial receive buffer.
            for (i=0;i<12;i=i+1) begin
                send_input(i,0);
                expect_output(i,0);
            end
            send_input(12,0);
            repeat (5) @(negedge aclk);
            if (m_axis_tvalid) $fatal(1,"In-flight word unexpectedly completed");
            if (scenario==0) control_word=1; else aresetn=0;
            repeat (20) begin
                @(negedge aclk);
                if (m_axis_tvalid || s_axis_tready || status_word!==32'h50460001)
                    $fatal(1,"Reset did not quarantine stream");
            end
            if (scenario==0) control_word=0; else aresetn=1;
            repeat (70) begin
                @(negedge aclk);
                if (m_axis_tvalid || status_word!==32'h50460000)
                    $fatal(1,"Stale stream data survived reset");
            end
            // Recovery must start at word zero and preserve all 80 TLAST positions.
            for (i=0;i<80;i=i+1) begin
                send_input(i,i==79);
                expect_output(i,i==79);
            end
        end
        $display("INFLIGHT_STREAM_RESET_PASS soft=1 external=1 partial_words=12 recovered_words=160 stale=0");
        $finish;
    end
    initial begin #10000000; $fatal(1,"In-flight stream regression timeout"); end
endmodule
