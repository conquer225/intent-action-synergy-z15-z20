`timescale 1ns/1ps
module tb_stream_control;
  reg aclk=0;always #5 aclk=~aclk;
  reg pclk=0;always #6.666 pclk=~pclk;
  reg cclk=0;always #10.416 cclk=~cclk;
  reg resetn=0,vs=0,de=0;reg [7:0] awaddr=4,araddr=0;
  reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
  reg [31:0] wdata=0;wire awready,wready,bvalid,arready,rvalid;
  wire [1:0] bresp,rresp;wire [31:0] rdata;wire [23:0] data;wire ode,ovs;
  vision_stream_control dut(.aclk(aclk),.aresetn(resetn),
    .s_axi_awaddr(awaddr),.s_axi_awprot(3'd0),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
    .s_axi_wdata(wdata),.s_axi_wstrb(4'hf),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
    .s_axi_bresp(bresp),.s_axi_bvalid(bvalid),.s_axi_bready(bready),
    .s_axi_araddr(araddr),.s_axi_arprot(3'd0),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
    .s_axi_rdata(rdata),.s_axi_rresp(rresp),.s_axi_rvalid(rvalid),.s_axi_rready(rready),
    .pix_clk(pclk),.cam_clk(cclk),.cam_vsync(vs),.in_data(24'hff0000),.in_de(de),.in_hsync(1'b0),.in_vsync(vs),
    .in_hblank(1'b0),.in_vblank(vs),.in_field(1'b0),.out_data(data),.out_de(ode),.out_vsync(ovs),
    .out_hsync(),.out_hblank(),.out_vblank(),.out_field());
  task read(input [7:0] addr,input [31:0] value);
    begin
      @(negedge aclk);araddr=addr;arvalid=1;
      do @(posedge aclk);while(!arready);
      @(negedge aclk);arvalid=0;
      wait(rvalid);#1;if(rdata!==value || rresp!=0)$fatal(1,"read %h got %h expected %h",addr,rdata,value);
      repeat(3)begin @(posedge aclk);#1;if(!rvalid || rdata!==value)$fatal(1,"read backpressure");end
      @(negedge aclk);rready=1;@(negedge aclk);rready=0;
    end
  endtask
  task write(input [31:0] value,input [1:0] response);
    begin
      @(negedge aclk);awvalid=1;
      do @(posedge aclk);while(!awready);
      @(negedge aclk);awvalid=0;repeat(3)@(negedge aclk);wdata=value;wvalid=1;
      do @(posedge aclk);while(!wready);
      @(negedge aclk);wvalid=0;
      wait(bvalid);#1;if(bresp!==response)$fatal(1,"write response");
      repeat(3)begin @(posedge aclk);#1;if(!bvalid || bresp!==response)$fatal(1,"write backpressure");end
      @(negedge aclk);bready=1;@(negedge aclk);bready=0;
    end
  endtask
  initial begin
    repeat(5)@(negedge aclk);resetn=1;repeat(8)@(negedge aclk);
    read(0,32'h56495332);write(32'h14,0);
    // Busy rejects a second request, and the first does not tear the frame.
    write(32'h11,2);read(4,0);
    @(negedge pclk);de=1;repeat(12)@(negedge pclk);
    if(data!==24'hff0000)$fatal(1,"mode changed before frame boundary");
    de=0;repeat(8)@(negedge pclk);vs=1;repeat(20)@(negedge pclk);vs=0;
    repeat(20)@(negedge aclk);read(4,32'h14);read(8,0);
    read(8'h10,1);
    @(negedge pclk);de=1;repeat(12)@(negedge pclk);
    if(data!==24'h4d4d4d)$fatal(1,"mode not applied after frame boundary");
    $display("STREAM_CONTROL_PASS independent clocks, frame commit, busy rejection, AXI backpressure");$finish;
  end
  initial begin #100000;$fatal(1,"timeout");end
endmodule
