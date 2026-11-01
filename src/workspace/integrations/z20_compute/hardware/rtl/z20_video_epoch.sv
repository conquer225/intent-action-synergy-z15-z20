// Passive monitor for an ordered, ID-less VDMA write channel. Never gates video.
// Static AW decode and B handshakes are pipelined together, one event per cycle.
module z20_video_epoch #(
 parameter [31:0] BASE=32'h01000000,
 parameter integer STRIDE=3840, HEIGHT=720, ACTIVE=1920
)(
 input wire clk, reset_n,
 input wire awvalid, awready,
 input wire [31:0] awaddr,
 input wire [7:0] awlen,
 input wire [2:0] awsize,
 input wire bvalid,bready,
 input wire [1:0] bresp,
 output reg [1:0] writer_index,completed_index,
 output reg [31:0] write_epoch,completed_sequence,
 output reg writer_valid,completed_valid,fault,
 output wire event_changed
);
 localparam integer PITCH=STRIDE*HEIGHT;
 reg [1:0] queue[0:63];
 reg [5:0] head,tail;
 reg [6:0] count;
 reg [6:0] pending[0:2];
 reg [2:0] last_seen;
 reg [31:0] next_address;
 reg [11:0] line_remaining;
 reg push,pop;
 reg [1:0] response;
 reg [31:0] address;
 reg [11:0] burst_bytes;
 reg [1:0] slot;
 reg address_ok,final_burst,first_burst;
 wire [32:0] decoded_bytes=({25'b0,awlen}+33'd1)<<awsize;
 wire [32:0] burst_end={1'b0,awaddr}+decoded_bytes;
 reg [2:0] region,valid_end,at_end,at_start;
 integer i;
 always @* begin
  for(integer k=0;k<3;k=k+1) begin
   region[k]=({1'b0,awaddr}>={1'b0,BASE}+k*PITCH &&
              {1'b0,awaddr}<{1'b0,BASE}+(k+1)*PITCH);
   valid_end[k]=(burst_end<={1'b0,BASE}+k*PITCH+(HEIGHT-1)*STRIDE+ACTIVE);
   at_end[k]=(burst_end=={1'b0,BASE}+k*PITCH+(HEIGHT-1)*STRIDE+ACTIVE);
   at_start[k]=(awaddr==BASE+k*PITCH);
  end
 end
 // Keep long constant-range decode off the state-dependent validity path.
 always @(posedge clk) begin
  if(!reset_n) begin
   push<=0;pop<=0;response<=0;address<=0;burst_bytes<=0;
   slot<=0;address_ok<=0;final_burst<=0;first_burst<=0;
  end else begin
   push<=awvalid && awready;pop<=bvalid && bready;response<=bresp;
   if(awvalid && awready) begin
    address<=awaddr;burst_bytes<=decoded_bytes[11:0];
    slot<=region[2] ? 2 : (region[1] ? 1 : 0);
    address_ok<=(awsize<=3 && |(region & valid_end));
    final_burst<=|(region & at_end);first_burst<=|at_start;
   end
  end
 end
 wire starting=push && (!writer_valid || writer_index!=slot || first_burst);
 wire [11:0] available=starting ? ACTIVE : line_remaining;
 wire completing=pop && count!=0 && pending[queue[head]]==1 &&
                 !(push && slot==queue[head]) && last_seen[queue[head]];
 wire invalid_transaction=(push && (!address_ok || (count==64 && !pop))) ||
             (pop && (count==0 || response!=0)) ||
             (starting && (pending[slot]!=0 || !first_burst)) ||
             (push && (burst_bytes>available || (!starting && address!=next_address)));
 assign event_changed=!fault && (starting || completing || invalid_transaction);
 always @(posedge clk) begin
  if(!reset_n) begin
   head<=0;tail<=0;count<=0;writer_index<=0;completed_index<=0;
   write_epoch<=0;completed_sequence<=0;writer_valid<=0;completed_valid<=0;
   fault<=0;last_seen<=0;next_address<=0;line_remaining<=ACTIVE;
   for(i=0;i<3;i=i+1) pending[i]<=0;
  end else if(!fault) begin
   if(invalid_transaction) begin fault<=1;completed_valid<=0;writer_valid<=0;end
   else begin
    case({push,pop})
     2'b10:count<=count+1;
     2'b01:count<=count-1;
     default:count<=count;
    endcase
    if(push) begin
     queue[tail]<=slot;tail<=tail+1;
     if(burst_bytes==available) begin
      next_address<=address+burst_bytes+STRIDE-ACTIVE;
      line_remaining<=ACTIVE;
     end else begin
      next_address<=address+burst_bytes;
      line_remaining<=available-burst_bytes;
     end
    end
    if(pop) head<=head+1;
    for(i=0;i<3;i=i+1) begin
     case({push && slot==i,pop && queue[head]==i})
      2'b10:pending[i]<=pending[i]+1;
      2'b01:pending[i]<=pending[i]-1;
      default:pending[i]<=pending[i];
     endcase
     if(starting && slot==i) last_seen[i]<=final_burst;
     else if(push && slot==i && final_burst) last_seen[i]<=1;
    end
    if(starting) begin
     writer_index<=slot;writer_valid<=1;write_epoch<=write_epoch+1;
    end
    if(completing) begin
     completed_index<=queue[head];completed_valid<=1;completed_sequence<=completed_sequence+1;
    end
   end
  end
 end
endmodule
