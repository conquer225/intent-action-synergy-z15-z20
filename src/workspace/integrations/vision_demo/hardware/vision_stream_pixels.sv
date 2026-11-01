`timescale 1ns/1ps
// SPDX-License-Identifier: MIT
// Fixed-latency pixel pipeline. There is no frame-ready or software-start input.
module vision_stream_pixels #(parameter WIDTH=1280, HEIGHT=720)(
  input wire clk,reset,enable,
  input wire [3:0] mode,
  input wire [23:0] in_rgb,
  input wire in_de,in_hsync,in_vsync,
  output reg [23:0] out_rgb,
  output reg out_de,out_hsync,out_vsync
);
  reg [23:0] rgb0,rgb1,rgb2,rgb3;
  reg [7:0] gray0,gray1,gray2,gray3;
  reg [3:0] mode0,mode1,mode2,mode3;
  reg [3:0] de_pipe,hs_pipe,vs_pipe,en_pipe;
  reg previous_de,previous_vs;
  reg [10:0] x,y,x0,y0;
  reg [7:0] phase0,phase1,phase2,phase3;
  reg [7:0] line_a,line_b;
  (* ram_style="block" *) reg [7:0] line1[0:WIDTH-1],line2[0:WIDTH-1];
  reg [7:0] a0,a1,b0,b1,c0,c1;
  reg [7:0] lo_a,mi_a,hi_a,lo_b,mi_b,hi_b,lo_c,mi_c,hi_c;
  reg [7:0] max_lo,mid_mi,min_hi,median3,edge2,edge3;
  reg signed [11:0] gx1,gy1;
  reg [3:0] border;
  wire [7:0] g=luminance(in_rgb);
  wire [7:0] equalized0;reg [7:0] equalized1,equalized2,equalized3;
  vision_stream_histogram #(.WIDTH(WIDTH),.HEIGHT(HEIGHT)) histogram(
    .clk(clk),.reset(reset),.enable(enable && mode==8),.de(in_de),.vs(in_vsync),.gray(g),.mapped(equalized0));
  localparam GRID_W=(WIDTH+3)/4,GRID_H=(HEIGHT+3)/4;
  // Quarter-resolution temporal analysis is an overlay, while the underlying
  // video remains full resolution. No DDR traffic or CPU history processing.
  (* ram_style="block" *) reg [23:0] history[0:GRID_W*GRID_H-1];
  reg [23:0] history0,forward_data;
  reg [15:0] address0,forward_address;
  reg forward_valid,warmed,had_pixels;reg [4:0] previous_mode;
  reg [7:0] delta1,trail1,delta2,trail2,delta3,trail3;
  wire [15:0] address=(y>>2)*GRID_W+(x>>2);
  wire [23:0] previous=forward_valid && address0==forward_address?forward_data:history0;
  wire [7:0] difference=gray0>previous[23:16]?gray0-previous[23:16]:previous[23:16]-gray0;
  wire [7:0] decayed=previous[15:8]-(previous[15:8]>>3)-(previous[15:8]!=0);
  wire [7:0] new_delta=warmed?difference:8'd0;
  wire [7:0] new_trail=!warmed?8'd0:(new_delta>decayed?new_delta:decayed);
  wire sample_cell=x0[1:0]==0 && y0[1:0]==0;
  function [7:0] low3(input [7:0] a,b,c);begin low3=a<b?(a<c?a:c):(b<c?b:c);end endfunction
  function [7:0] high3(input [7:0] a,b,c);begin high3=a>b?(a>c?a:c):(b>c?b:c);end endfunction
  function [7:0] middle3(input [7:0] a,b,c);
    begin middle3=a>b?(b>c?b:(a>c?c:a)):(a>c?a:(b>c?c:b));end
  endfunction
  function [11:0] absolute(input signed [11:0] a);begin absolute=a<0?-a:a;end endfunction
  function [7:0] saturated(input [9:0] a);begin saturated=a>255?255:a[7:0];end endfunction
  // Cyan, violet and rose with a slow spatial hue sweep. Flat areas preserve
  // a darkened real image; edges are coloured without enlarging noise pixels.
  function [23:0] glow(input [23:0] base,input [7:0] strength,input [7:0] hue,input dark);
    reg [7:0] r,b,gc; reg [9:0] rr,gg,bb;
    begin
      r=(strength*(64+{1'b0,hue[7:1]}))>>8;
      gc=(strength*(255-{1'b0,hue[7:1]}))>>8;
      b=strength;
      rr=(dark?(base[23:16]>>3):(base[23:16]>>1))+{2'b0,r};
      gg=(dark?(base[15:8]>>3):(base[15:8]>>1))+{2'b0,gc};
      bb=(dark?(base[7:0]>>3):(base[7:0]>>1))+{2'b0,b};
      glow={saturated(rr),saturated(gg),saturated(bb)};
    end
  endfunction
  wire [12:0] edge_sum={1'b0,absolute(gx1)}+{1'b0,absolute(gy1)};
  function [7:0] luminance(input [23:0] p);
    reg [15:0] v;
    begin v=77*p[23:16]+150*p[15:8]+29*p[7:0]+128;luminance=v[15:8];end
  endfunction
  always @(posedge clk) begin
    if(reset) begin
      de_pipe<=0;hs_pipe<=0;vs_pipe<=0;en_pipe<=0;
      out_de<=0;out_hsync<=0;out_vsync<=0;out_rgb<=0;
      previous_de<=0;previous_vs<=0;x<=0;y<=0;border<=0;
      forward_valid<=0;warmed<=0;had_pixels<=0;previous_mode<=0;
    end else begin
      previous_de<=in_de;previous_vs<=in_vsync;
      if(in_vsync && !previous_vs)begin x<=0;y<=0;end
      else if(in_de)x<=x==WIDTH-1?0:x+1'b1;
      else if(previous_de)begin x<=0;y<=y+1'b1;end
      x0<=x;y0<=y;
      if(in_de)had_pixels<=1;
      if(in_vsync && !previous_vs)begin
        warmed<=had_pixels && previous_mode=={enable,mode};had_pixels<=0;
        previous_mode<={enable,mode};forward_valid<=0;
      end
      if({enable,mode}!=previous_mode)begin warmed<=0;forward_valid<=0;end
      if(in_de && x<WIDTH)begin
        line_a<=line1[x];line_b<=line2[x];
        line1[x]<=g;line2[x]<=line1[x];
        if(y<HEIGHT)history0<=history[address];
      end
      address0<=address;
      border<={border[2:0],x<2 || y<2};
      phase0<=x[10:3];phase1<=phase0;phase2<=phase1;phase3<=phase2;
      if(de_pipe[0])begin
        if(sample_cell)begin
          history[address0]<={gray0,new_trail,new_delta};
          forward_data<={gray0,new_trail,new_delta};forward_address<=address0;forward_valid<=1;
          delta1<=new_delta;trail1<=new_trail;
        end else begin delta1<=warmed?previous[7:0]:8'd0;trail1<=warmed?previous[15:8]:8'd0;end
        a0<=a1;a1<=line_b;b0<=b1;b1<=line_a;c0<=c1;c1<=gray0;
        lo_a<=low3(a0,a1,line_b);mi_a<=middle3(a0,a1,line_b);hi_a<=high3(a0,a1,line_b);
        lo_b<=low3(b0,b1,line_a);mi_b<=middle3(b0,b1,line_a);hi_b<=high3(b0,b1,line_a);
        lo_c<=low3(c0,c1,gray0);mi_c<=middle3(c0,c1,gray0);hi_c<=high3(c0,c1,gray0);
        gx1<=- $signed({1'b0,a0})+$signed({1'b0,line_b})-2*$signed({1'b0,b0})+2*$signed({1'b0,line_a})-$signed({1'b0,c0})+$signed({1'b0,gray0});
        gy1<=- $signed({1'b0,a0})-2*$signed({1'b0,a1})-$signed({1'b0,line_b})+$signed({1'b0,c0})+2*$signed({1'b0,c1})+$signed({1'b0,gray0});
      end
      max_lo<=high3(lo_a,lo_b,lo_c);mid_mi<=middle3(mi_a,mi_b,mi_c);min_hi<=low3(hi_a,hi_b,hi_c);
      median3<=middle3(max_lo,mid_mi,min_hi);
      edge2<=edge_sum>255?255:edge_sum[7:0];edge3<=edge2;
      delta2<=delta1;trail2<=trail1;delta3<=delta2;trail3<=trail2;
      equalized1<=equalized0;equalized2<=equalized1;equalized3<=equalized2;
      de_pipe<={de_pipe[2:0],in_de};hs_pipe<={hs_pipe[2:0],in_hsync};
      vs_pipe<={vs_pipe[2:0],in_vsync};en_pipe<={en_pipe[2:0],enable};
      rgb0<=in_rgb;rgb1<=rgb0;rgb2<=rgb1;rgb3<=rgb2;
      gray0<=luminance(in_rgb);gray1<=gray0;gray2<=gray1;gray3<=gray2;
      mode0<=mode;mode1<=mode0;mode2<=mode1;mode3<=mode2;
      out_de<=de_pipe[3];out_hsync<=hs_pipe[3];out_vsync<=vs_pipe[3];
      out_rgb<=rgb3;
      if(en_pipe[3]) case(mode3)
        1:out_rgb<=glow(rgb3,border[3] || edge3<32?8'd0:(edge3>127?8'd255:{edge3[6:0],1'b0}),phase3,1'b1);
        2:out_rgb<=glow(rgb3,trail3>16?(trail3>63?8'd255:{trail3[5:0],2'b0}):8'd0,phase3,1'b0);
        3:out_rgb<=glow(rgb3,delta3>20?(delta3>63?8'd255:{delta3[5:0],2'b0}):8'd0,8'd220,1'b1);
        4:out_rgb<={gray3,gray3,gray3};
        5:out_rgb<=gray3>127?24'hffffff:24'h000000;
        6:out_rgb<=border[3]?{gray3,gray3,gray3}:{median3,median3,median3};
        7:out_rgb<=border[3]?{gray3,gray3,gray3}:{edge3,edge3,edge3};
        8:out_rgb<={equalized3,equalized3,equalized3};
        default:out_rgb<=rgb3;
      endcase
    end
  end
endmodule
