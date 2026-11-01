// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vtb_moment6_stream.h for the primary calling header

#include "verilated.h"

#include "Vtb_moment6_stream__Syms.h"
#include "Vtb_moment6_stream___024root.h"

extern const VlWide<9>/*287:0*/ Vtb_moment6_stream__ConstPool__CONST_h9a2fc1c8_0;
extern const VlWide<32>/*1023:0*/ Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0;

VL_INLINE_OPT VlCoroutine Vtb_moment6_stream___024root___eval_initial__TOP__0(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___eval_initial__TOP__0\n"); );
    // Init
    SData/*15:0*/ tb_moment6_stream__DOT____Vlvbound_h196af492__0;
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 = 0;
    CData/*0:0*/ __Vtask_tb_moment6_stream__DOT__send__0__first;
    __Vtask_tb_moment6_stream__DOT__send__0__first = 0;
    CData/*0:0*/ __Vtask_tb_moment6_stream__DOT__send__0__last;
    __Vtask_tb_moment6_stream__DOT__send__0__last = 0;
    IData/*31:0*/ __Vtask_tb_moment6_stream__DOT__send__0__seed;
    __Vtask_tb_moment6_stream__DOT__send__0__seed = 0;
    CData/*0:0*/ __Vtask_tb_moment6_stream__DOT__send__1__first;
    __Vtask_tb_moment6_stream__DOT__send__1__first = 0;
    CData/*0:0*/ __Vtask_tb_moment6_stream__DOT__send__1__last;
    __Vtask_tb_moment6_stream__DOT__send__1__last = 0;
    IData/*31:0*/ __Vtask_tb_moment6_stream__DOT__send__1__seed;
    __Vtask_tb_moment6_stream__DOT__send__1__seed = 0;
    CData/*0:0*/ __Vtask_tb_moment6_stream__DOT__send__2__first;
    __Vtask_tb_moment6_stream__DOT__send__2__first = 0;
    CData/*0:0*/ __Vtask_tb_moment6_stream__DOT__send__2__last;
    __Vtask_tb_moment6_stream__DOT__send__2__last = 0;
    IData/*31:0*/ __Vtask_tb_moment6_stream__DOT__send__2__seed;
    __Vtask_tb_moment6_stream__DOT__send__2__seed = 0;
    // Body
    co_await vlSelf->__VtrigSched_hd18aefb6__0.trigger(
                                                       "@(negedge tb_moment6_stream.clk)", 
                                                       "tb_moment6_stream.sv", 
                                                       30);
    co_await vlSelf->__VtrigSched_hd18aefb6__0.trigger(
                                                       "@(negedge tb_moment6_stream.clk)", 
                                                       "tb_moment6_stream.sv", 
                                                       30);
    co_await vlSelf->__VtrigSched_hd18aefb6__0.trigger(
                                                       "@(negedge tb_moment6_stream.clk)", 
                                                       "tb_moment6_stream.sv", 
                                                       30);
    vlSelf->tb_moment6_stream__DOT__rst_n = 1U;
    __Vtask_tb_moment6_stream__DOT__send__0__seed = 1U;
    __Vtask_tb_moment6_stream__DOT__send__0__last = 0U;
    __Vtask_tb_moment6_stream__DOT__send__0__first = 1U;
    co_await vlSelf->__VtrigSched_hd18aefb6__0.trigger(
                                                       "@(negedge tb_moment6_stream.clk)", 
                                                       "tb_moment6_stream.sv", 
                                                       13);
    vlSelf->tb_moment6_stream__DOT__valid_i = 1U;
    vlSelf->tb_moment6_stream__DOT__start_i = __Vtask_tb_moment6_stream__DOT__send__0__first;
    vlSelf->tb_moment6_stream__DOT__last_i = __Vtask_tb_moment6_stream__DOT__send__0__last;
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 
        = (0xffffU & __Vtask_tb_moment6_stream__DOT__send__0__seed);
    vlSelf->tb_moment6_stream__DOT__sample_i[0U] = 
        ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__sample_i[0U]) 
         | (IData)(tb_moment6_stream__DOT____Vlvbound_h196af492__0));
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 
        = (0xffffU & ((IData)(1U) + __Vtask_tb_moment6_stream__DOT__send__0__seed));
    vlSelf->tb_moment6_stream__DOT__sample_i[0U] = 
        ((0xffffU & vlSelf->tb_moment6_stream__DOT__sample_i[0U]) 
         | ((IData)(tb_moment6_stream__DOT____Vlvbound_h196af492__0) 
            << 0x10U));
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 
        = (0xffffU & ((IData)(2U) + __Vtask_tb_moment6_stream__DOT__send__0__seed));
    vlSelf->tb_moment6_stream__DOT__sample_i[1U] = 
        ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__sample_i[1U]) 
         | (IData)(tb_moment6_stream__DOT____Vlvbound_h196af492__0));
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 
        = (0xffffU & ((IData)(3U) + __Vtask_tb_moment6_stream__DOT__send__0__seed));
    vlSelf->tb_moment6_stream__DOT__sample_i[1U] = 
        ((0xffffU & vlSelf->tb_moment6_stream__DOT__sample_i[1U]) 
         | ((IData)(tb_moment6_stream__DOT____Vlvbound_h196af492__0) 
            << 0x10U));
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 
        = (0xffffU & ((IData)(4U) + __Vtask_tb_moment6_stream__DOT__send__0__seed));
    vlSelf->tb_moment6_stream__DOT__sample_i[2U] = 
        ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__sample_i[2U]) 
         | (IData)(tb_moment6_stream__DOT____Vlvbound_h196af492__0));
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 
        = (0xffffU & ((IData)(5U) + __Vtask_tb_moment6_stream__DOT__send__0__seed));
    vlSelf->tb_moment6_stream__DOT__sample_i[2U] = 
        ((0xffffU & vlSelf->tb_moment6_stream__DOT__sample_i[2U]) 
         | ((IData)(tb_moment6_stream__DOT____Vlvbound_h196af492__0) 
            << 0x10U));
    co_await vlSelf->__VtrigSched_hd18aeef7__0.trigger(
                                                       "@(posedge tb_moment6_stream.clk)", 
                                                       "tb_moment6_stream.sv", 
                                                       19);
    co_await vlSelf->__VdlySched.delay(1U, "tb_moment6_stream.sv", 
                                       20);
    if (VL_UNLIKELY(((IData)(vlSelf->tb_moment6_stream__DOT__result_valid_o) 
                     != (IData)(__Vtask_tb_moment6_stream__DOT__send__0__last)))) {
        VL_WRITEF("[%0t] %%Error: tb_moment6_stream.sv:22: Assertion failed in %Ntb_moment6_stream.send: result framing mismatch\n",
                  64,VL_TIME_UNITED_Q(1),-12,vlSymsp->name());
        VL_STOP_MT("tb_moment6_stream.sv", 22, "");
    }
    co_await vlSelf->__VtrigSched_hd18aefb6__0.trigger(
                                                       "@(negedge tb_moment6_stream.clk)", 
                                                       "tb_moment6_stream.sv", 
                                                       23);
    vlSelf->tb_moment6_stream__DOT__valid_i = 0U;
    vlSelf->tb_moment6_stream__DOT__start_i = 0U;
    vlSelf->tb_moment6_stream__DOT__last_i = 0U;
    co_await vlSelf->__VtrigSched_hd18aefb6__0.trigger(
                                                       "@(negedge tb_moment6_stream.clk)", 
                                                       "tb_moment6_stream.sv", 
                                                       33);
    co_await vlSelf->__VtrigSched_hd18aefb6__0.trigger(
                                                       "@(negedge tb_moment6_stream.clk)", 
                                                       "tb_moment6_stream.sv", 
                                                       33);
    __Vtask_tb_moment6_stream__DOT__send__1__seed = 0xfffffffeU;
    __Vtask_tb_moment6_stream__DOT__send__1__last = 1U;
    __Vtask_tb_moment6_stream__DOT__send__1__first = 0U;
    co_await vlSelf->__VtrigSched_hd18aefb6__0.trigger(
                                                       "@(negedge tb_moment6_stream.clk)", 
                                                       "tb_moment6_stream.sv", 
                                                       13);
    vlSelf->tb_moment6_stream__DOT__valid_i = 1U;
    vlSelf->tb_moment6_stream__DOT__start_i = __Vtask_tb_moment6_stream__DOT__send__1__first;
    vlSelf->tb_moment6_stream__DOT__last_i = __Vtask_tb_moment6_stream__DOT__send__1__last;
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 
        = (0xffffU & __Vtask_tb_moment6_stream__DOT__send__1__seed);
    vlSelf->tb_moment6_stream__DOT__sample_i[0U] = 
        ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__sample_i[0U]) 
         | (IData)(tb_moment6_stream__DOT____Vlvbound_h196af492__0));
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 
        = (0xffffU & ((IData)(1U) + __Vtask_tb_moment6_stream__DOT__send__1__seed));
    vlSelf->tb_moment6_stream__DOT__sample_i[0U] = 
        ((0xffffU & vlSelf->tb_moment6_stream__DOT__sample_i[0U]) 
         | ((IData)(tb_moment6_stream__DOT____Vlvbound_h196af492__0) 
            << 0x10U));
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 
        = (0xffffU & ((IData)(2U) + __Vtask_tb_moment6_stream__DOT__send__1__seed));
    vlSelf->tb_moment6_stream__DOT__sample_i[1U] = 
        ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__sample_i[1U]) 
         | (IData)(tb_moment6_stream__DOT____Vlvbound_h196af492__0));
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 
        = (0xffffU & ((IData)(3U) + __Vtask_tb_moment6_stream__DOT__send__1__seed));
    vlSelf->tb_moment6_stream__DOT__sample_i[1U] = 
        ((0xffffU & vlSelf->tb_moment6_stream__DOT__sample_i[1U]) 
         | ((IData)(tb_moment6_stream__DOT____Vlvbound_h196af492__0) 
            << 0x10U));
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 
        = (0xffffU & ((IData)(4U) + __Vtask_tb_moment6_stream__DOT__send__1__seed));
    vlSelf->tb_moment6_stream__DOT__sample_i[2U] = 
        ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__sample_i[2U]) 
         | (IData)(tb_moment6_stream__DOT____Vlvbound_h196af492__0));
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 
        = (0xffffU & ((IData)(5U) + __Vtask_tb_moment6_stream__DOT__send__1__seed));
    vlSelf->tb_moment6_stream__DOT__sample_i[2U] = 
        ((0xffffU & vlSelf->tb_moment6_stream__DOT__sample_i[2U]) 
         | ((IData)(tb_moment6_stream__DOT____Vlvbound_h196af492__0) 
            << 0x10U));
    co_await vlSelf->__VtrigSched_hd18aeef7__0.trigger(
                                                       "@(posedge tb_moment6_stream.clk)", 
                                                       "tb_moment6_stream.sv", 
                                                       19);
    co_await vlSelf->__VdlySched.delay(1U, "tb_moment6_stream.sv", 
                                       20);
    if (VL_UNLIKELY(((IData)(vlSelf->tb_moment6_stream__DOT__result_valid_o) 
                     != (IData)(__Vtask_tb_moment6_stream__DOT__send__1__last)))) {
        VL_WRITEF("[%0t] %%Error: tb_moment6_stream.sv:22: Assertion failed in %Ntb_moment6_stream.send: result framing mismatch\n",
                  64,VL_TIME_UNITED_Q(1),-12,vlSymsp->name());
        VL_STOP_MT("tb_moment6_stream.sv", 22, "");
    }
    co_await vlSelf->__VtrigSched_hd18aefb6__0.trigger(
                                                       "@(negedge tb_moment6_stream.clk)", 
                                                       "tb_moment6_stream.sv", 
                                                       23);
    vlSelf->tb_moment6_stream__DOT__valid_i = 0U;
    vlSelf->tb_moment6_stream__DOT__start_i = 0U;
    vlSelf->tb_moment6_stream__DOT__last_i = 0U;
    if (VL_UNLIKELY((2U != (IData)(vlSelf->tb_moment6_stream__DOT__dut__DOT__count_q)))) {
        VL_WRITEF("[%0t] %%Error: tb_moment6_stream.sv:35: Assertion failed in %Ntb_moment6_stream: first count mismatch\n",
                  64,VL_TIME_UNITED_Q(1),-12,vlSymsp->name());
        VL_STOP_MT("tb_moment6_stream.sv", 35, "");
    }
    if (VL_UNLIKELY((0xffffffffffffULL != (0xffffffffffffULL 
                                           & (((QData)((IData)(
                                                               vlSelf->tb_moment6_stream__DOT__sums_o[1U])) 
                                               << 0x20U) 
                                              | (QData)((IData)(
                                                                vlSelf->tb_moment6_stream__DOT__sums_o[0U]))))))) {
        VL_WRITEF("[%0t] %%Error: tb_moment6_stream.sv:38: Assertion failed in %Ntb_moment6_stream.unnamedblk2: sum[0] mismatch\n",
                  64,VL_TIME_UNITED_Q(1),-12,vlSymsp->name());
        VL_STOP_MT("tb_moment6_stream.sv", 38, "");
    }
    if (VL_UNLIKELY((1ULL != (0xffffffffffffULL & (
                                                   ((QData)((IData)(
                                                                    vlSelf->tb_moment6_stream__DOT__sums_o[2U])) 
                                                    << 0x10U) 
                                                   | ((QData)((IData)(
                                                                      vlSelf->tb_moment6_stream__DOT__sums_o[1U])) 
                                                      >> 0x10U)))))) {
        VL_WRITEF("[%0t] %%Error: tb_moment6_stream.sv:38: Assertion failed in %Ntb_moment6_stream.unnamedblk2: sum[1] mismatch\n",
                  64,VL_TIME_UNITED_Q(1),-12,vlSymsp->name());
        VL_STOP_MT("tb_moment6_stream.sv", 38, "");
    }
    if (VL_UNLIKELY((3ULL != (0xffffffffffffULL & (
                                                   ((QData)((IData)(
                                                                    vlSelf->tb_moment6_stream__DOT__sums_o[4U])) 
                                                    << 0x20U) 
                                                   | (QData)((IData)(
                                                                     vlSelf->tb_moment6_stream__DOT__sums_o[3U]))))))) {
        VL_WRITEF("[%0t] %%Error: tb_moment6_stream.sv:38: Assertion failed in %Ntb_moment6_stream.unnamedblk2: sum[2] mismatch\n",
                  64,VL_TIME_UNITED_Q(1),-12,vlSymsp->name());
        VL_STOP_MT("tb_moment6_stream.sv", 38, "");
    }
    if (VL_UNLIKELY((5ULL != (0xffffffffffffULL & (
                                                   ((QData)((IData)(
                                                                    vlSelf->tb_moment6_stream__DOT__sums_o[5U])) 
                                                    << 0x10U) 
                                                   | ((QData)((IData)(
                                                                      vlSelf->tb_moment6_stream__DOT__sums_o[4U])) 
                                                      >> 0x10U)))))) {
        VL_WRITEF("[%0t] %%Error: tb_moment6_stream.sv:38: Assertion failed in %Ntb_moment6_stream.unnamedblk2: sum[3] mismatch\n",
                  64,VL_TIME_UNITED_Q(1),-12,vlSymsp->name());
        VL_STOP_MT("tb_moment6_stream.sv", 38, "");
    }
    if (VL_UNLIKELY((7ULL != (0xffffffffffffULL & (
                                                   ((QData)((IData)(
                                                                    vlSelf->tb_moment6_stream__DOT__sums_o[7U])) 
                                                    << 0x20U) 
                                                   | (QData)((IData)(
                                                                     vlSelf->tb_moment6_stream__DOT__sums_o[6U]))))))) {
        VL_WRITEF("[%0t] %%Error: tb_moment6_stream.sv:38: Assertion failed in %Ntb_moment6_stream.unnamedblk2: sum[4] mismatch\n",
                  64,VL_TIME_UNITED_Q(1),-12,vlSymsp->name());
        VL_STOP_MT("tb_moment6_stream.sv", 38, "");
    }
    if (VL_UNLIKELY((9ULL != (0xffffffffffffULL & (
                                                   ((QData)((IData)(
                                                                    vlSelf->tb_moment6_stream__DOT__sums_o[8U])) 
                                                    << 0x10U) 
                                                   | ((QData)((IData)(
                                                                      vlSelf->tb_moment6_stream__DOT__sums_o[7U])) 
                                                      >> 0x10U)))))) {
        VL_WRITEF("[%0t] %%Error: tb_moment6_stream.sv:38: Assertion failed in %Ntb_moment6_stream.unnamedblk2: sum[5] mismatch\n",
                  64,VL_TIME_UNITED_Q(1),-12,vlSymsp->name());
        VL_STOP_MT("tb_moment6_stream.sv", 38, "");
    }
    if (VL_UNLIKELY((5ULL != (0xffffffffffffULL & (
                                                   ((QData)((IData)(
                                                                    vlSelf->tb_moment6_stream__DOT__cross_o[1U])) 
                                                    << 0x20U) 
                                                   | (QData)((IData)(
                                                                     vlSelf->tb_moment6_stream__DOT__cross_o[0U]))))))) {
        VL_WRITEF("[%0t] %%Error: tb_moment6_stream.sv:41: Assertion failed in %Ntb_moment6_stream: gram[0,0]\n",
                  64,VL_TIME_UNITED_Q(1),-12,vlSymsp->name());
        VL_STOP_MT("tb_moment6_stream.sv", 41, "");
    }
    if (VL_UNLIKELY((4ULL != (0xffffffffffffULL & (
                                                   ((QData)((IData)(
                                                                    vlSelf->tb_moment6_stream__DOT__cross_o[2U])) 
                                                    << 0x10U) 
                                                   | ((QData)((IData)(
                                                                      vlSelf->tb_moment6_stream__DOT__cross_o[1U])) 
                                                      >> 0x10U)))))) {
        VL_WRITEF("[%0t] %%Error: tb_moment6_stream.sv:42: Assertion failed in %Ntb_moment6_stream: gram[0,1]\n",
                  64,VL_TIME_UNITED_Q(1),-12,vlSymsp->name());
        VL_STOP_MT("tb_moment6_stream.sv", 42, "");
    }
    __Vtask_tb_moment6_stream__DOT__send__2__seed = 7U;
    __Vtask_tb_moment6_stream__DOT__send__2__last = 1U;
    __Vtask_tb_moment6_stream__DOT__send__2__first = 1U;
    co_await vlSelf->__VtrigSched_hd18aefb6__0.trigger(
                                                       "@(negedge tb_moment6_stream.clk)", 
                                                       "tb_moment6_stream.sv", 
                                                       13);
    vlSelf->tb_moment6_stream__DOT__valid_i = 1U;
    vlSelf->tb_moment6_stream__DOT__start_i = __Vtask_tb_moment6_stream__DOT__send__2__first;
    vlSelf->tb_moment6_stream__DOT__last_i = __Vtask_tb_moment6_stream__DOT__send__2__last;
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 
        = (0xffffU & __Vtask_tb_moment6_stream__DOT__send__2__seed);
    vlSelf->tb_moment6_stream__DOT__sample_i[0U] = 
        ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__sample_i[0U]) 
         | (IData)(tb_moment6_stream__DOT____Vlvbound_h196af492__0));
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 
        = (0xffffU & ((IData)(1U) + __Vtask_tb_moment6_stream__DOT__send__2__seed));
    vlSelf->tb_moment6_stream__DOT__sample_i[0U] = 
        ((0xffffU & vlSelf->tb_moment6_stream__DOT__sample_i[0U]) 
         | ((IData)(tb_moment6_stream__DOT____Vlvbound_h196af492__0) 
            << 0x10U));
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 
        = (0xffffU & ((IData)(2U) + __Vtask_tb_moment6_stream__DOT__send__2__seed));
    vlSelf->tb_moment6_stream__DOT__sample_i[1U] = 
        ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__sample_i[1U]) 
         | (IData)(tb_moment6_stream__DOT____Vlvbound_h196af492__0));
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 
        = (0xffffU & ((IData)(3U) + __Vtask_tb_moment6_stream__DOT__send__2__seed));
    vlSelf->tb_moment6_stream__DOT__sample_i[1U] = 
        ((0xffffU & vlSelf->tb_moment6_stream__DOT__sample_i[1U]) 
         | ((IData)(tb_moment6_stream__DOT____Vlvbound_h196af492__0) 
            << 0x10U));
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 
        = (0xffffU & ((IData)(4U) + __Vtask_tb_moment6_stream__DOT__send__2__seed));
    vlSelf->tb_moment6_stream__DOT__sample_i[2U] = 
        ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__sample_i[2U]) 
         | (IData)(tb_moment6_stream__DOT____Vlvbound_h196af492__0));
    tb_moment6_stream__DOT____Vlvbound_h196af492__0 
        = (0xffffU & ((IData)(5U) + __Vtask_tb_moment6_stream__DOT__send__2__seed));
    vlSelf->tb_moment6_stream__DOT__sample_i[2U] = 
        ((0xffffU & vlSelf->tb_moment6_stream__DOT__sample_i[2U]) 
         | ((IData)(tb_moment6_stream__DOT____Vlvbound_h196af492__0) 
            << 0x10U));
    co_await vlSelf->__VtrigSched_hd18aeef7__0.trigger(
                                                       "@(posedge tb_moment6_stream.clk)", 
                                                       "tb_moment6_stream.sv", 
                                                       19);
    co_await vlSelf->__VdlySched.delay(1U, "tb_moment6_stream.sv", 
                                       20);
    if (VL_UNLIKELY(((IData)(vlSelf->tb_moment6_stream__DOT__result_valid_o) 
                     != (IData)(__Vtask_tb_moment6_stream__DOT__send__2__last)))) {
        VL_WRITEF("[%0t] %%Error: tb_moment6_stream.sv:22: Assertion failed in %Ntb_moment6_stream.send: result framing mismatch\n",
                  64,VL_TIME_UNITED_Q(1),-12,vlSymsp->name());
        VL_STOP_MT("tb_moment6_stream.sv", 22, "");
    }
    co_await vlSelf->__VtrigSched_hd18aefb6__0.trigger(
                                                       "@(negedge tb_moment6_stream.clk)", 
                                                       "tb_moment6_stream.sv", 
                                                       23);
    vlSelf->tb_moment6_stream__DOT__valid_i = 0U;
    vlSelf->tb_moment6_stream__DOT__start_i = 0U;
    vlSelf->tb_moment6_stream__DOT__last_i = 0U;
    if (VL_UNLIKELY((((1U != (IData)(vlSelf->tb_moment6_stream__DOT__dut__DOT__count_q)) 
                      | (7ULL != (0xffffffffffffULL 
                                  & (((QData)((IData)(
                                                      vlSelf->tb_moment6_stream__DOT__sums_o[1U])) 
                                      << 0x20U) | (QData)((IData)(
                                                                  vlSelf->tb_moment6_stream__DOT__sums_o[0U])))))) 
                     | (0x31ULL != (0xffffffffffffULL 
                                    & (((QData)((IData)(
                                                        vlSelf->tb_moment6_stream__DOT__cross_o[1U])) 
                                        << 0x20U) | (QData)((IData)(
                                                                    vlSelf->tb_moment6_stream__DOT__cross_o[0U])))))))) {
        VL_WRITEF("[%0t] %%Error: tb_moment6_stream.sv:46: Assertion failed in %Ntb_moment6_stream: second frame did not clear first\n",
                  64,VL_TIME_UNITED_Q(1),-12,vlSymsp->name());
        VL_STOP_MT("tb_moment6_stream.sv", 46, "");
    }
    co_await vlSelf->__VtrigSched_hd18aefb6__0.trigger(
                                                       "@(negedge tb_moment6_stream.clk)", 
                                                       "tb_moment6_stream.sv", 
                                                       47);
    vlSelf->tb_moment6_stream__DOT__rst_n = 0U;
    co_await vlSelf->__VtrigSched_hd18aeef7__0.trigger(
                                                       "@(posedge tb_moment6_stream.clk)", 
                                                       "tb_moment6_stream.sv", 
                                                       49);
    co_await vlSelf->__VdlySched.delay(1U, "tb_moment6_stream.sv", 
                                       50);
    if (VL_UNLIKELY(((((IData)(vlSelf->tb_moment6_stream__DOT__result_valid_o) 
                       | (0U != (IData)(vlSelf->tb_moment6_stream__DOT__dut__DOT__count_q))) 
                      | (0U != (((((((((Vtb_moment6_stream__ConstPool__CONST_h9a2fc1c8_0[0U] 
                                        ^ vlSelf->tb_moment6_stream__DOT__sums_o[0U]) 
                                       | (Vtb_moment6_stream__ConstPool__CONST_h9a2fc1c8_0[1U] 
                                          ^ vlSelf->tb_moment6_stream__DOT__sums_o[1U])) 
                                      | (Vtb_moment6_stream__ConstPool__CONST_h9a2fc1c8_0[2U] 
                                         ^ vlSelf->tb_moment6_stream__DOT__sums_o[2U])) 
                                     | (Vtb_moment6_stream__ConstPool__CONST_h9a2fc1c8_0[3U] 
                                        ^ vlSelf->tb_moment6_stream__DOT__sums_o[3U])) 
                                    | (Vtb_moment6_stream__ConstPool__CONST_h9a2fc1c8_0[4U] 
                                       ^ vlSelf->tb_moment6_stream__DOT__sums_o[4U])) 
                                   | (Vtb_moment6_stream__ConstPool__CONST_h9a2fc1c8_0[5U] 
                                      ^ vlSelf->tb_moment6_stream__DOT__sums_o[5U])) 
                                  | (Vtb_moment6_stream__ConstPool__CONST_h9a2fc1c8_0[6U] 
                                     ^ vlSelf->tb_moment6_stream__DOT__sums_o[6U])) 
                                 | (Vtb_moment6_stream__ConstPool__CONST_h9a2fc1c8_0[7U] 
                                    ^ vlSelf->tb_moment6_stream__DOT__sums_o[7U])) 
                                | (Vtb_moment6_stream__ConstPool__CONST_h9a2fc1c8_0[8U] 
                                   ^ vlSelf->tb_moment6_stream__DOT__sums_o[8U])))) 
                     | (0U != (((((((((((((((((((((
                                                   (((((((((((Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0U] 
                                                              ^ 
                                                              vlSelf->tb_moment6_stream__DOT__cross_o[0U]) 
                                                             | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[1U] 
                                                                ^ 
                                                                vlSelf->tb_moment6_stream__DOT__cross_o[1U])) 
                                                            | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[2U] 
                                                               ^ 
                                                               vlSelf->tb_moment6_stream__DOT__cross_o[2U])) 
                                                           | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[3U] 
                                                              ^ 
                                                              vlSelf->tb_moment6_stream__DOT__cross_o[3U])) 
                                                          | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[4U] 
                                                             ^ 
                                                             vlSelf->tb_moment6_stream__DOT__cross_o[4U])) 
                                                         | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[5U] 
                                                            ^ 
                                                            vlSelf->tb_moment6_stream__DOT__cross_o[5U])) 
                                                        | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[6U] 
                                                           ^ 
                                                           vlSelf->tb_moment6_stream__DOT__cross_o[6U])) 
                                                       | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[7U] 
                                                          ^ 
                                                          vlSelf->tb_moment6_stream__DOT__cross_o[7U])) 
                                                      | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[8U] 
                                                         ^ 
                                                         vlSelf->tb_moment6_stream__DOT__cross_o[8U])) 
                                                     | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[9U] 
                                                        ^ 
                                                        vlSelf->tb_moment6_stream__DOT__cross_o[9U])) 
                                                    | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0xaU] 
                                                       ^ 
                                                       vlSelf->tb_moment6_stream__DOT__cross_o[0xaU])) 
                                                   | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0xbU] 
                                                      ^ 
                                                      vlSelf->tb_moment6_stream__DOT__cross_o[0xbU])) 
                                                  | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0xcU] 
                                                     ^ 
                                                     vlSelf->tb_moment6_stream__DOT__cross_o[0xcU])) 
                                                 | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0xdU] 
                                                    ^ 
                                                    vlSelf->tb_moment6_stream__DOT__cross_o[0xdU])) 
                                                | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0xeU] 
                                                   ^ 
                                                   vlSelf->tb_moment6_stream__DOT__cross_o[0xeU])) 
                                               | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0xfU] 
                                                  ^ 
                                                  vlSelf->tb_moment6_stream__DOT__cross_o[0xfU])) 
                                              | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0x10U] 
                                                 ^ 
                                                 vlSelf->tb_moment6_stream__DOT__cross_o[0x10U])) 
                                             | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0x11U] 
                                                ^ vlSelf->tb_moment6_stream__DOT__cross_o[0x11U])) 
                                            | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0x12U] 
                                               ^ vlSelf->tb_moment6_stream__DOT__cross_o[0x12U])) 
                                           | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0x13U] 
                                              ^ vlSelf->tb_moment6_stream__DOT__cross_o[0x13U])) 
                                          | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0x14U] 
                                             ^ vlSelf->tb_moment6_stream__DOT__cross_o[0x14U])) 
                                         | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0x15U] 
                                            ^ vlSelf->tb_moment6_stream__DOT__cross_o[0x15U])) 
                                        | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0x16U] 
                                           ^ vlSelf->tb_moment6_stream__DOT__cross_o[0x16U])) 
                                       | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0x17U] 
                                          ^ vlSelf->tb_moment6_stream__DOT__cross_o[0x17U])) 
                                      | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0x18U] 
                                         ^ vlSelf->tb_moment6_stream__DOT__cross_o[0x18U])) 
                                     | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0x19U] 
                                        ^ vlSelf->tb_moment6_stream__DOT__cross_o[0x19U])) 
                                    | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0x1aU] 
                                       ^ vlSelf->tb_moment6_stream__DOT__cross_o[0x1aU])) 
                                   | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0x1bU] 
                                      ^ vlSelf->tb_moment6_stream__DOT__cross_o[0x1bU])) 
                                  | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0x1cU] 
                                     ^ vlSelf->tb_moment6_stream__DOT__cross_o[0x1cU])) 
                                 | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0x1dU] 
                                    ^ vlSelf->tb_moment6_stream__DOT__cross_o[0x1dU])) 
                                | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0x1eU] 
                                   ^ vlSelf->tb_moment6_stream__DOT__cross_o[0x1eU])) 
                               | (Vtb_moment6_stream__ConstPool__CONST_h7faf6f7f_0[0x1fU] 
                                  ^ vlSelf->tb_moment6_stream__DOT__cross_o[0x1fU])))))) {
        VL_WRITEF("[%0t] %%Error: tb_moment6_stream.sv:52: Assertion failed in %Ntb_moment6_stream: reset mismatch\n",
                  64,VL_TIME_UNITED_Q(1),-12,vlSymsp->name());
        VL_STOP_MT("tb_moment6_stream.sv", 52, "");
    }
    VL_WRITEF("PASS moment6_stream framing, sums, products, stall, reset\n");
    VL_FINISH_MT("tb_moment6_stream.sv", 54, "");
}

#ifdef VL_DEBUG
VL_ATTR_COLD void Vtb_moment6_stream___024root___dump_triggers__act(Vtb_moment6_stream___024root* vlSelf);
#endif  // VL_DEBUG

void Vtb_moment6_stream___024root___eval_triggers__act(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___eval_triggers__act\n"); );
    // Body
    vlSelf->__VactTriggered.at(0U) = ((IData)(vlSelf->tb_moment6_stream__DOT__clk) 
                                      & (~ (IData)(vlSelf->__Vtrigrprev__TOP__tb_moment6_stream__DOT__clk)));
    vlSelf->__VactTriggered.at(1U) = vlSelf->__VdlySched.awaitingCurrentTime();
    vlSelf->__VactTriggered.at(2U) = ((~ (IData)(vlSelf->tb_moment6_stream__DOT__clk)) 
                                      & (IData)(vlSelf->__Vtrigrprev__TOP__tb_moment6_stream__DOT__clk));
    vlSelf->__Vtrigrprev__TOP__tb_moment6_stream__DOT__clk 
        = vlSelf->tb_moment6_stream__DOT__clk;
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vtb_moment6_stream___024root___dump_triggers__act(vlSelf);
    }
#endif
}
