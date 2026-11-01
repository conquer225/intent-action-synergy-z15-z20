`timescale 1ns/1ps
// Calibration stores eight consecutive valid samples. Directions: 0 invalid, 1 L, 2 C, 3 R.
module gaze_control #(parameter STALL_CYCLES=12500000,DWELL_FRAMES=15,RELEASE_FRAMES=6)(
 input wire clk,rst,clear,input wire sample,feature_valid,input wire [8:0] cx,
 input wire [1:0] calibrate,
 output reg [1:0] direction,output reg valid,output reg [2:0] calibrated,
 output reg [1:0] cal_active,output reg cal_error,
 output reg [8:0] left_x,center_x,right_x,
 output reg commit,output reg [1:0] commit_direction,output reg [15:0] event_seq,
 output reg stale);
 reg [23:0] watchdog;reg [2:0] cal_n;reg [11:0] cal_sum;
 reg [8:0] cal_min,cal_max;
 reg [7:0] dwell,release_n;reg [1:0] previous;reg armed;
 wire [9:0] dl=cx>=left_x?cx-left_x:left_x-cx;
 wire [9:0] dc=cx>=center_x?cx-center_x:center_x-cx;
 wire [9:0] dr=cx>=right_x?cx-right_x:right_x-cx;
 wire ordered=((left_x+10'd6<=center_x && center_x+10'd6<=right_x) || (right_x+10'd6<=center_x && center_x+10'd6<=left_x));
 reg [1:0] candidate;
 always @* begin
  candidate=0;
  if(calibrated==7&&ordered&&feature_valid)begin
   if(dl+2<dc && dl+2<dr && dl<=24)candidate=1;
   else if(dc+2<dl && dc+2<dr && dc<=24)candidate=2;
   else if(dr+2<dl && dr+2<dc && dr<=24)candidate=3;
  end
 end
 always @(posedge clk)begin
  commit<=0;
  if(rst||clear)begin direction<=0;valid<=0;calibrated<=0;cal_active<=0;cal_error<=0;left_x<=0;center_x<=0;right_x<=0;event_seq<=0;commit_direction<=0;watchdog<=0;stale<=1;cal_n<=0;cal_sum<=0;dwell<=0;release_n<=0;previous<=0;armed<=1;cal_min<=0;cal_max<=0;end
  else begin
   if(watchdog<STALL_CYCLES)watchdog<=watchdog+1'b1;
   else begin stale<=1;valid<=0;direction<=0;dwell<=0;release_n<=0;previous<=0;cal_n<=0;cal_sum<=0;end
   if(calibrate!=0)begin
    cal_active<=calibrate;cal_n<=0;cal_sum<=0;cal_error<=0;
    case(calibrate)1:calibrated[0]<=0;2:calibrated[1]<=0;3:calibrated[2]<=0;endcase
    valid<=0;direction<=0;dwell<=0;release_n<=0;previous<=0;armed<=1;
   end else if(sample)begin
    watchdog<=0;stale<=0;
    if(cal_active!=0)begin
     valid<=0;direction<=0;
     if(feature_valid && (cal_n==0 || ({1'b0,cx}<={1'b0,cal_min}+6 && {1'b0,cx}+6>={1'b0,cal_max})))begin
      if(cal_n==0)begin cal_min<=cx;cal_max<=cx;end
      else begin if(cx<cal_min)cal_min<=cx;if(cx>cal_max)cal_max<=cx;end
      cal_sum<=cal_sum+cx;cal_n<=cal_n+1'b1;
      if(cal_n==7)begin
       case(cal_active)
        1:begin left_x<=(cal_sum+{3'b0,cx})>>3;calibrated[0]<=1;end
        2:begin center_x<=(cal_sum+{3'b0,cx})>>3;calibrated[1]<=1;end
        3:begin right_x<=(cal_sum+{3'b0,cx})>>3;calibrated[2]<=1;end
       endcase
       cal_active<=0;
      end
     end else begin cal_n<=0;cal_sum<=0;end
    end else begin
     cal_error<=calibrated==7&&!ordered;
     direction<=candidate;valid<=candidate!=0;
     if(candidate==0)begin dwell<=0;release_n<=0;previous<=0;end
     else if(candidate==2)begin
      dwell<=0;previous<=2;
      if(release_n<RELEASE_FRAMES)release_n<=release_n+1'b1;
      if(release_n>=RELEASE_FRAMES-1)armed<=1;
     end else begin
      release_n<=0;previous<=candidate;
      if(candidate!=previous)dwell<=1;
      else if(dwell<DWELL_FRAMES)dwell<=dwell+1'b1;
      if(armed && candidate==previous && dwell>=DWELL_FRAMES-1)begin
       commit<=1;commit_direction<=candidate;event_seq<=event_seq+1'b1;armed<=0;
      end
     end
    end
   end
  end
 end
endmodule
