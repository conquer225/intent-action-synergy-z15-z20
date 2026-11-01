`timescale 1ns/1ps
module tb_signal_axi;
reg clk=0,rst=0;always #5 clk=~clk;
reg [7:0] aw=0,ar=0;reg [31:0] wd=0,ind=0;reg av=0,wv=0,rv=0,iv=0,il=0;
wire aready,wready,rready,iready,bv,ov,ol;wire [1:0] br,rr;wire [31:0] rd,outd;
signal_core dut(.aclk(clk),.aresetn(rst),.s_axis_tdata(ind),.s_axis_tvalid(iv),.s_axis_tready(iready),.s_axis_tlast(il),
 .m_axis_tdata(outd),.m_axis_tvalid(ov),.m_axis_tready(1'b1),.m_axis_tlast(ol),
 .s_axi_awaddr(aw),.s_axi_awvalid(av),.s_axi_awready(aready),.s_axi_wdata(wd),.s_axi_wstrb(4'hf),.s_axi_wvalid(wv),.s_axi_wready(wready),
 .s_axi_bresp(br),.s_axi_bvalid(bv),.s_axi_bready(1'b1),.s_axi_araddr(ar),.s_axi_arvalid(rv),.s_axi_arready(rready),
 .s_axi_rdata(rd),.s_axi_rresp(rr),.s_axi_rvalid(),.s_axi_rready(1'b1));
task write(input [7:0] addr,input [31:0] value,input [1:0] response);begin
 @(negedge clk);aw=addr;av=1;while(!aready)@(negedge clk);
 @(negedge clk);av=0;repeat(2)@(negedge clk);wd=value;wv=1;while(!wready)@(negedge clk);
 @(negedge clk);wv=0;while(!bv)@(negedge clk);if(br!=response)$fatal(1,"AXIL response");@(negedge clk);
end endtask
task read(input [7:0] addr,input [31:0] value);begin
 @(negedge clk);ar=addr;rv=1;while(!rready)@(negedge clk);@(negedge clk);rv=0;
 if(rd!=value || rr!=0)$fatal(1,"AXIL independent statistics %h expected %d actual %d",addr,value,rd);
end endtask
task sample(input integer value,input integer expected,input bit last);begin
 @(negedge clk);ind=value;iv=1;il=last;while(!iready)@(negedge clk);
 @(negedge clk);iv=0;if(!ov || $signed(outd)!=expected || ol!=last)$fatal(1,"sample signed/parity/TLAST");
end endtask
initial begin
 #20;rst=1;read(0,32'h53494731);write(12,0,2);write(8,65537,2);
 sample(-1000,-250,0);sample(1000,62,1);
 write(12,2,0);write(16,2,0);write(4,3,0);
 sample(1,1,0);sample(10,10,0);sample(3,3,0);sample(14,14,1);
 write(20,0,0);read(32,1);read(36,4);read(44,10);
 write(20,1,0);read(32,1);read(36,24);read(44,296);read(24,4);
 write(4,3,0);read(24,0);read(32,0);read(36,0);
 $display("AXIL split write, invalid config, signed arithmetic, two-channel sum/squares and clear PASS");$finish;
end
initial begin #100000;$fatal(1,"timeout");end
endmodule
