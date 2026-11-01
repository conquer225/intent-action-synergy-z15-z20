`timescale 1ns/1ps
// Signed Q16/integer samples; 1..8 interleaved channels. Data TLAST is DMA packet end.
module signal_core(
 (* X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF s_axis:m_axis:s_axi, ASSOCIATED_RESET aresetn" *) input wire aclk,
 (* X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *) input wire aresetn,
 input wire [31:0] s_axis_tdata,input wire s_axis_tvalid,output wire s_axis_tready,input wire s_axis_tlast,
 output reg [31:0] m_axis_tdata,output reg m_axis_tvalid,input wire m_axis_tready,output reg m_axis_tlast,
 input wire [7:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
 input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,input wire s_axi_wvalid,output wire s_axi_wready,
 output reg [1:0] s_axi_bresp,output reg s_axi_bvalid,input wire s_axi_bready,
 input wire [7:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
 output reg [31:0] s_axi_rdata,output reg [1:0] s_axi_rresp,output reg s_axi_rvalid,input wire s_axi_rready
);
 reg [7:0] address; reg have_address; reg [31:0] data; reg [3:0] strobes; reg have_data;
 reg [16:0] coefficient; reg [3:0] channels; reg [15:0] window_size; reg bypass;
 reg [2:0] channel,read_channel;
 reg signed [31:0] history[0:7]; reg [15:0] count[0:7];
 reg signed [63:0] sum[0:7],finished_sum[0:7]; reg [63:0] squares[0:7],finished_squares[0:7];
 reg [31:0] windows[0:7],samples,saturation;
 wire signed [32:0] difference=$signed(s_axis_tdata)-$signed(history[channel]);
 wire signed [50:0] product=difference*$signed({1'b0,coefficient});
 wire signed [51:0] candidate=$signed(history[channel])+(product>>>16);
 wire too_high=candidate>52'sd2147483647,too_low=candidate< -52'sd2147483648;
 wire signed [31:0] filtered=bypass?$signed(s_axis_tdata):too_high?32'sh7fffffff:too_low?32'sh80000000:candidate[31:0];
 wire signed [63:0] square=$signed(filtered)*$signed(filtered);
 wire [64:0] next_squares={1'b0,squares[channel]}+{1'b0,square};
 assign s_axis_tready=(!m_axis_tvalid || m_axis_tready) && !have_address && !have_data;
 assign s_axi_awready=!have_address && !s_axi_bvalid;
 assign s_axi_wready=!have_data && !s_axi_bvalid;
 assign s_axi_arready=!s_axi_rvalid;
 integer i;
 always @(posedge aclk) begin
  if(!aresetn) begin
   coefficient<=16384;channels<=1;window_size<=50;bypass<=0;channel<=0;read_channel<=0;
   m_axis_tvalid<=0;m_axis_tdata<=0;m_axis_tlast<=0; samples<=0;saturation<=0;
   have_address<=0;have_data<=0;address<=0;data<=0;strobes<=0;
   s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_rdata<=0;
   for(i=0;i<8;i=i+1)begin history[i]<=0;count[i]<=0;sum[i]<=0;squares[i]<=0;windows[i]<=0;finished_sum[i]<=0;finished_squares[i]<=0;end
  end else begin
   if(m_axis_tvalid && m_axis_tready)m_axis_tvalid<=0;
   if(s_axis_tvalid && s_axis_tready) begin
    m_axis_tdata<=filtered;m_axis_tlast<=s_axis_tlast;m_axis_tvalid<=1;history[channel]<=filtered;
    samples<=samples+1;channel<=channel+1>=channels?0:channel+1;
    if(too_high || too_low || next_squares[64])saturation<=saturation+1;
    if(count[channel]+1>=window_size)begin
     finished_sum[channel]<=sum[channel]+filtered;
     finished_squares[channel]<=next_squares[64]?64'hffffffffffffffff:next_squares[63:0];
     windows[channel]<=windows[channel]+1;count[channel]<=0;sum[channel]<=0;squares[channel]<=0;
    end else begin
     count[channel]<=count[channel]+1;sum[channel]<=sum[channel]+filtered;
     squares[channel]<=next_squares[64]?64'hffffffffffffffff:next_squares[63:0];
    end
   end
   if(s_axi_awvalid && s_axi_awready)begin address<=s_axi_awaddr;have_address<=1;end
   if(s_axi_wvalid && s_axi_wready)begin data<=s_axi_wdata;strobes<=s_axi_wstrb;have_data<=1;end
   if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
   if(have_address && have_data && !s_axi_bvalid)begin
    have_address<=0;have_data<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
    if(strobes!=4'b1111)s_axi_bresp<=2;
    else case(address)
     8'h04:begin
      bypass<=data[1];
      if(data[0])begin
       channel<=0;samples<=0;saturation<=0;m_axis_tvalid<=0;
       for(i=0;i<8;i=i+1)begin history[i]<=0;count[i]<=0;sum[i]<=0;squares[i]<=0;windows[i]<=0;finished_sum[i]<=0;finished_squares[i]<=0;end
      end
     end
     8'h08:if(data<=65536)coefficient<=data[16:0];else s_axi_bresp<=2;
     8'h0c:if(data>=1 && data<=8)channels<=data[3:0];else s_axi_bresp<=2;
     8'h10:if(data>=1 && data<=65535)window_size<=data[15:0];else s_axi_bresp<=2;
     8'h14:if(data<8)read_channel<=data[2:0];else s_axi_bresp<=2;
     default:s_axi_bresp<=2;
    endcase
   end
   if(s_axi_rvalid && s_axi_rready)s_axi_rvalid<=0;
   if(s_axi_arvalid && s_axi_arready)begin
    s_axi_rvalid<=1;s_axi_rresp<=0;
    case(s_axi_araddr)
     8'h00:s_axi_rdata<=32'h53494731;
     8'h04:s_axi_rdata<={30'b0,bypass,1'b0};
     8'h08:s_axi_rdata<={15'b0,coefficient};8'h0c:s_axi_rdata<={28'b0,channels};
     8'h10:s_axi_rdata<={16'b0,window_size};8'h14:s_axi_rdata<={29'b0,read_channel};
     8'h18:s_axi_rdata<=samples;8'h1c:s_axi_rdata<=saturation;
     8'h20:s_axi_rdata<=windows[read_channel];8'h24:s_axi_rdata<=finished_sum[read_channel][31:0];
     8'h28:s_axi_rdata<=finished_sum[read_channel][63:32];8'h2c:s_axi_rdata<=finished_squares[read_channel][31:0];
     8'h30:s_axi_rdata<=finished_squares[read_channel][63:32];
     default:begin s_axi_rdata<=0;s_axi_rresp<=2;end
    endcase
   end
  end
 end
endmodule
