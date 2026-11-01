`timescale 1ns/1ps
module tb_live_osd;
    reg aclk=0,pix_clk=0,resetn=0;always #5 aclk=~aclk;always #7 pix_clk=~pix_clk;
    integer hx=0,vy=0;
    always @(posedge pix_clk)if(!resetn)begin hx<=0;vy<=0;end else if(hx==191)begin hx<=0;vy<=vy==99?0:vy+1;end else hx<=hx+1;
    wire de=hx<128 && vy>=10 && vy<90;wire hs=hx>=160 && hx<176;wire vs=vy<2;
    wire [23:0] data={hx[7:0],vy[7:0],8'h35};
    reg [7:0] awaddr=0,araddr=0;reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
    reg [31:0] wdata=0;reg [3:0] wstrb=15;wire awready,wready,bvalid,arready,rvalid;
    wire [1:0] bresp,rresp;wire [31:0] rdata;wire [23:0] outdata;wire outde,ouths,outvs,outhb,outvb,outfield;
    live_osd #(.WIDTH(128),.HEIGHT(80),.PIXEL_HZ(1152000)) dut(
        .aclk(aclk),.aresetn(resetn),.s_axi_awaddr(awaddr),.s_axi_awprot(3'b0),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
        .s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
        .s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),
        .s_axi_araddr(araddr),.s_axi_arprot(3'b0),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
        .s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready),
        .pix_clk(pix_clk),.cam_vsync(vs),.in_data(data),.in_de(de),.in_hsync(hs),.in_vsync(vs),
        .in_hblank(hx>=128),.in_vblank(vy<10 || vy>=90),.in_field(1'b0),
        .out_data(outdata),.out_de(outde),.out_hsync(ouths),.out_vsync(outvs),.out_hblank(outhb),.out_vblank(outvb),.out_field(outfield));
    reg saved_de,saved_hs,saved_vs,saved_hb,saved_vb,saved_enabled;reg [23:0] saved_data;integer checked=0;
    always @(posedge pix_clk)begin
        saved_de=de;saved_hs=hs;saved_vs=vs;saved_hb=hx>=128;saved_vb=vy<10||vy>=90;saved_data=data;saved_enabled=dut.renderer.enabled;
        if(dut.pix_resetn)begin
            #1;
            if({outde,ouths,outvs,outhb,outvb,outfield}!={saved_de,saved_hs,saved_vs,saved_hb,saved_vb,1'b0})$fatal(1,"Pixel/sync misalignment");
            if(!saved_enabled && outdata!==saved_data)$fatal(1,"Disabled OSD changed pixels");
            checked=checked+1;
        end
    end
    task automatic write_reg(input [7:0] addr,input [31:0] value,input integer skew,input [1:0] expect_resp);
        begin
            @(negedge aclk);awaddr=addr;wdata=value;
            if(skew<0)begin
                wvalid=1;do @(posedge aclk);while(!wready);@(negedge aclk);wvalid=0;
                repeat(3)@(negedge aclk);awvalid=1;do @(posedge aclk);while(!awready);@(negedge aclk);awvalid=0;
            end else begin
                awvalid=1;do @(posedge aclk);while(!awready);@(negedge aclk);awvalid=0;
                repeat(skew)@(negedge aclk);wvalid=1;do @(posedge aclk);while(!wready);@(negedge aclk);wvalid=0;
            end
            wait(bvalid);if(bresp!==expect_resp)$fatal(1,"AXI response addr=%h got=%d expected=%d",addr,bresp,expect_resp);
            repeat(3)begin @(negedge aclk);if(!bvalid || bresp!==expect_resp)$fatal(1,"B response not held");end
            bready=1;@(negedge aclk);bready=0;
        end
    endtask
    task automatic read_reg(input [7:0] addr,output [31:0] value);
        begin
            @(negedge aclk);araddr=addr;arvalid=1;do @(posedge aclk);while(!arready);@(negedge aclk);arvalid=0;
            wait(rvalid);value=rdata;if(rresp!=0)$fatal(1,"AXI read error");
            repeat(3)begin @(negedge aclk);if(!rvalid || value!==rdata)$fatal(1,"R response not held");end
            rready=1;@(negedge aclk);rready=0;
        end
    endtask
    task automatic next_frame;begin @(posedge vs);repeat(4)@(negedge pix_clk);end endtask
    task automatic commit;begin write_reg(8,1,0,0);wait(!dut.busy);end endtask
    task automatic pixel_check(input integer px,py,input [23:0] expected);
        begin
            do @(negedge pix_clk);while(!(de && dut.renderer.x==px && dut.renderer.y==py));
            @(posedge pix_clk);#2;if(outdata!==expected)$fatal(1,"Pixel %d,%d got=%h expected=%h",px,py,outdata,expected);
        end
    endtask
    reg [31:0] value,count0;integer before_x,before_age,k;
    initial begin
        repeat(8)@(negedge aclk);resetn=1;next_frame();
        read_reg(0,value);if(value!==32'h4f534438)$fatal(1,"ID");
        write_reg(32,1,3,0);write_reg(36,1,-1,0);write_reg(40,0,0,0);
        write_reg(44,500,0,0);write_reg(48,100,0,0);write_reg(52,2,0,0);
        write_reg(64,{16'd30,16'd10},0,0);write_reg(68,{16'd50,16'd30},0,0);write_reg(72,24'hffff00,0,0);
        next_frame();write_reg(8,1,0,0);write_reg(8,1,0,2);
        write_reg(64,{16'd30,16'd60},0,0); // must not alter the held commit
        wait(!dut.busy);
        if(dut.renderer.cur_x0[0]!=10)$fatal(1,"Mailbox payload mutated before acknowledgement");
        pixel_check(10,30,24'hffff00);
        write_reg(68,{16'd50,16'd80},0,0);commit();before_x=dut.renderer.cur_x0[0];
        if(before_x!=10)$fatal(1,"New target jumped immediately");
        for(k=0;k<20;k=k+1)begin
            next_frame();
            if(dut.renderer.cur_x0[0]<before_x || dut.renderer.cur_x0[0]>60)$fatal(1,"Interpolation overshoot");
            before_x=dut.renderer.cur_x0[0];
        end
        if(before_x!=60)$fatal(1,"Interpolation did not converge");
        before_age=dut.renderer.age[0];write_reg(36,0,0,0);commit();
        if(dut.renderer.age[0]<before_age)$fatal(1,"Miss renewed lifetime");
        pixel_check(60,30,24'h808080);
        read_reg(12,count0);
        repeat(40)begin commit();end
        repeat(10)@(negedge aclk); // allow the registered Gray counter to cross domains
        read_reg(12,value);if(value-count0<40)$fatal(1,"Video stopped: before=%d after=%d",count0,value);
        if(dut.renderer.age[0]<600)$fatal(1,"Retained result never expired");
        pixel_check(60,30,{8'd60,8'd40,8'h35});
        write_reg(36,1,0,0);write_reg(64,{16'd30,16'd70},0,0);write_reg(68,{16'd50,16'd90},0,0);commit();
        if(dut.renderer.cur_x0[0]!=70)$fatal(1,"Reacquisition must snap after expiry");
        write_reg(40,1000,0,0);commit();pixel_check(70,30,{8'd70,8'd40,8'h35});
        write_reg(40,0,0,0);write_reg(64,{16'd30,16'd150},0,0);commit();
        if(dut.renderer.confirmed[0])$fatal(1,"Invalid geometry accepted");
        write_reg(32,3,0,0);commit();if(dut.renderer.age[0]!=65535)$fatal(1,"Explicit clear");
        write_reg(32,0,0,0);commit();next_frame();
        if(checked<100000)$fatal(1,"Insufficient pixel checks");
        $display("PASS tb_live_osd: %0d aligned pixels; independent clocks, split AXI channels, atomic hold, smooth motion, miss retention/gray/expiry, stale input and clear",checked);$finish;
    end
    initial begin #500000000;$fatal(1,"Test timeout");end
endmodule
