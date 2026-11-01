// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design internal header
// See Vtb_moment6_stream.h for the primary calling header

#ifndef VERILATED_VTB_MOMENT6_STREAM___024ROOT_H_
#define VERILATED_VTB_MOMENT6_STREAM___024ROOT_H_  // guard

#include "verilated.h"
#include "verilated_timing.h"

class Vtb_moment6_stream__Syms;

class Vtb_moment6_stream___024root final : public VerilatedModule {
  public:

    // DESIGN SPECIFIC STATE
    // Anonymous structures to workaround compiler member-count bugs
    struct {
        CData/*0:0*/ tb_moment6_stream__DOT__clk;
        CData/*0:0*/ tb_moment6_stream__DOT__rst_n;
        CData/*0:0*/ tb_moment6_stream__DOT__valid_i;
        CData/*0:0*/ tb_moment6_stream__DOT__start_i;
        CData/*0:0*/ tb_moment6_stream__DOT__last_i;
        CData/*0:0*/ tb_moment6_stream__DOT__result_valid_o;
        CData/*0:0*/ __Vdlyvval__tb_moment6_stream__DOT__clk__v0;
        CData/*0:0*/ __Vdlyvset__tb_moment6_stream__DOT__clk__v0;
        CData/*0:0*/ __Vtrigrprev__TOP__tb_moment6_stream__DOT__clk;
        CData/*0:0*/ __VactContinue;
        SData/*15:0*/ tb_moment6_stream__DOT__dut__DOT__count_q;
        VlWide<3>/*95:0*/ tb_moment6_stream__DOT__sample_i;
        VlWide<9>/*287:0*/ tb_moment6_stream__DOT__sums_o;
        VlWide<32>/*1007:0*/ tb_moment6_stream__DOT__cross_o;
        IData/*31:0*/ __VstlIterCount;
        IData/*31:0*/ __VactIterCount;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__x_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__x_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__x_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__x_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__x_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__x_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__product_ext;
    };
    struct {
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__product_ext;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__accum;
        QData/*47:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__product_ext;
    };
    VlDelayScheduler __VdlySched;
    VlTriggerScheduler __VtrigSched_hd18aefb6__0;
    VlTriggerScheduler __VtrigSched_hd18aeef7__0;
    VlTriggerVec<1> __VstlTriggered;
    VlTriggerVec<3> __VactTriggered;
    VlTriggerVec<3> __VnbaTriggered;

    // INTERNAL VARIABLES
    Vtb_moment6_stream__Syms* const vlSymsp;

    // CONSTRUCTORS
    Vtb_moment6_stream___024root(Vtb_moment6_stream__Syms* symsp, const char* v__name);
    ~Vtb_moment6_stream___024root();
    VL_UNCOPYABLE(Vtb_moment6_stream___024root);

    // INTERNAL METHODS
    void __Vconfigure(bool first);
} VL_ATTR_ALIGNED(VL_CACHE_LINE_BYTES);


#endif  // guard
