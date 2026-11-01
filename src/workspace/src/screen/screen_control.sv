`timescale 1ns/1ps
// mode: 0 setup, 1/2/3 calibration targets, 4 run, 5 calibration failed.
module screen_control #(
 parameter MS_CYCLES=50000,SETTLE_MS=2000,CAL_TIMEOUT_MS=15000,
 parameter CAL_SAMPLES=16,DWELL_MS=750,RELEASE_MS=350,STALL_MS=250)(
 input wire clk,rst,clear,start,preview,sample,ready,blocked,
 input wire [1:0] eye_valid,input wire [7:0] ratio0,ratio1,
 input wire [9:0] ref_x0,ref_x1,input wire [8:0] ref_y0,ref_y1,
 output reg [2:0] mode,output reg settled,output reg [4:0] cal_count,
 output reg [2:0] calibrated,output reg [1:0] direction,output reg valid,stale,
 output reg [3:0] reason,progress,output reg armed,commit,
 output reg [15:0] event_seq,output reg [1:0] event_direction,
 output reg [7:0] l0,c0,r0,l1,c1,r1);
 reg [15:0] ms_tick,stage_ms,stall_ms,dwell_ms,release_ms;
 reg [31:0] ms_div;
 reg [15:0] sum0,sum1;reg [7:0] min0,max0,min1,max1;
 reg [9:0] anchor_x0,anchor_x1;reg [8:0] anchor_y0,anchor_y1;
 reg [1:0] candidate_previous;reg [2:0] stable_n;
 wire tick=ms_div==MS_CYCLES-1;
 function automatic [10:0] distance(input [10:0] a,b);distance=a>=b?a-b:b-a;endfunction
 function automatic ordered(input [7:0] a,b,c);
  ordered=(a+9'd6<=b&&b+9'd6<=c)||(c+9'd6<=b&&b+9'd6<=a);
 endfunction
 function automatic [1:0] choose(input [7:0] value,a,b,c);
  reg [8:0] da,db,dc;
  begin
   da=distance(value,a);db=distance(value,b);dc=distance(value,c);choose=0;
   if(da+1<db&&da+1<dc&&da<=32)choose=1;
   else if(db+1<da&&db+1<dc&&db<=32)choose=2;
   else if(dc+1<da&&dc+1<db&&dc<=32)choose=3;
  end
 endfunction
 wire [1:0] pick0=choose(ratio0,l0,c0,r0),pick1=choose(ratio1,l1,c1,r1);
 wire geometry_ok=distance(ref_x0,anchor_x0)<=16&&distance(ref_x1,anchor_x1)<=16&&
  distance(ref_y0,anchor_y0)<=10&&distance(ref_y1,anchor_y1)<=10&&
  distance(distance(ref_x0,ref_x1),distance(anchor_x0,anchor_x1))<=12;
 wire good=ready&&!blocked&&eye_valid==3;
 wire stable_cal=cal_count==0||(ratio0+9'd10>=max0&&ratio0<=min0+9'd10&&ratio1+9'd10>=max1&&ratio1<=min1+9'd10);
 wire [1:0] candidate=(good&&geometry_ok&&pick0==pick1)?pick0:2'd0;
 always @(posedge clk)begin
  commit<=0;
  if(rst||clear||preview||start)begin
   mode<=start?1:0;settled<=0;cal_count<=0;calibrated<=0;direction<=0;valid<=0;stale<=1;
   reason<=start?5:8;progress<=0;armed<=1;event_seq<=0;event_direction<=0;
   l0<=0;c0<=0;r0<=0;l1<=0;c1<=0;r1<=0;
   ms_div<=0;ms_tick<=0;stage_ms<=0;stall_ms<=0;dwell_ms<=0;release_ms<=0;
   sum0<=0;sum1<=0;min0<=0;max0<=0;min1<=0;max1<=0;
   anchor_x0<=0;anchor_x1<=0;anchor_y0<=0;anchor_y1<=0;stable_n<=0;candidate_previous<=0;
  end else begin
   if(tick)ms_div<=0;else ms_div<=ms_div+1'b1;
   if(tick)begin
    if(stall_ms<STALL_MS)stall_ms<=stall_ms+1'b1;
    if(mode>=1&&mode<=3)begin
     if(stage_ms<CAL_TIMEOUT_MS)stage_ms<=stage_ms+1'b1;
     else begin mode<=5;reason<=6;calibrated<=0;valid<=0;end
     if(stage_ms>=SETTLE_MS)settled<=1;
    end
    if(mode==4&&valid&&!blocked&&ready&&stall_ms<STALL_MS&&(!sample||candidate==direction))begin
     if(direction==2)begin
      dwell_ms<=0;progress<=0;
      if(release_ms<RELEASE_MS)release_ms<=release_ms+1'b1;
      if(release_ms>=RELEASE_MS-1)armed<=1;
     end else if(direction==1||direction==3)begin
      release_ms<=0;
      if(armed)begin
       if(dwell_ms<DWELL_MS)dwell_ms<=dwell_ms+1'b1;
       progress<=dwell_ms*15/DWELL_MS;
       if(dwell_ms>=DWELL_MS-1)begin commit<=1;event_seq<=event_seq+1'b1;event_direction<=direction;armed<=0;progress<=15;end
      end
     end
    end
   end
   if(blocked||!ready||stall_ms>=STALL_MS)begin
    valid<=0;direction<=0;dwell_ms<=0;release_ms<=0;progress<=0;stable_n<=0;candidate_previous<=0;
    if(stall_ms>=STALL_MS)stale<=1;
    reason<=!ready?1:blocked?7:9;
    if(mode>=1&&mode<=3)begin cal_count<=0;sum0<=0;sum1<=0;end
   end
   if(sample)begin
    stall_ms<=0;stale<=0;
    if(mode>=1&&mode<=3)begin
     valid<=0;direction<=0;progress<=0;reason<=!ready?1:blocked?7:eye_valid!=3?2:5;
     if(settled)begin
      if(good&&stable_cal&&(mode==1||geometry_ok))begin
       if(cal_count==0)begin min0<=ratio0;max0<=ratio0;min1<=ratio1;max1<=ratio1;end
       else begin
        if(ratio0<min0)min0<=ratio0;if(ratio0>max0)max0<=ratio0;
        if(ratio1<min1)min1<=ratio1;if(ratio1>max1)max1<=ratio1;
       end
       cal_count<=cal_count+1'b1;sum0<=sum0+ratio0;sum1<=sum1+ratio1;
       if(cal_count==CAL_SAMPLES-1)begin
        case(mode)
         1:begin
          l0<=(sum0+ratio0)/CAL_SAMPLES;l1<=(sum1+ratio1)/CAL_SAMPLES;calibrated<=1;
          anchor_x0<=ref_x0;anchor_x1<=ref_x1;anchor_y0<=ref_y0;anchor_y1<=ref_y1;
         end
         2:begin c0<=(sum0+ratio0)/CAL_SAMPLES;c1<=(sum1+ratio1)/CAL_SAMPLES;calibrated<=3;end
         3:begin r0<=(sum0+ratio0)/CAL_SAMPLES;r1<=(sum1+ratio1)/CAL_SAMPLES;calibrated<=7;end
        endcase
        mode<=mode+1'b1;stage_ms<=0;settled<=0;cal_count<=0;sum0<=0;sum1<=0;
       end
      end else begin
       cal_count<=0;sum0<=0;sum1<=0;
       if(good&&mode!=1&&!geometry_ok)reason<=3;
      end
     end
    end else if(mode==4)begin
     if(!ordered(l0,c0,r0)||!ordered(l1,c1,r1))begin mode<=5;reason<=6;valid<=0;direction<=0;calibrated<=0;end
     else if(candidate==0)begin
      valid<=0;direction<=0;stable_n<=0;candidate_previous<=0;dwell_ms<=0;release_ms<=0;progress<=0;
      reason<=!ready?1:blocked?7:eye_valid!=3?2:!geometry_ok?3:4;
     end else begin
      reason<=0;candidate_previous<=candidate;
      if(candidate!=candidate_previous)begin
       stable_n<=1;valid<=0;direction<=0;dwell_ms<=0;release_ms<=0;progress<=0;
      end else begin
       if(stable_n<3)stable_n<=stable_n+1'b1;
       if(stable_n>=2)begin valid<=1;direction<=candidate;end
      end
     end
    end
   end
  end
 end
endmodule
