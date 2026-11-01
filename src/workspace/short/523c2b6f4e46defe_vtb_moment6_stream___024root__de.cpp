// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vtb_moment6_stream.h for the primary calling header

#include "verilated.h"

#include "Vtb_moment6_stream___024root.h"

VlCoroutine Vtb_moment6_stream___024root___eval_initial__TOP__0(Vtb_moment6_stream___024root* vlSelf);
VlCoroutine Vtb_moment6_stream___024root___eval_initial__TOP__1(Vtb_moment6_stream___024root* vlSelf);

void Vtb_moment6_stream___024root___eval_initial(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___eval_initial\n"); );
    // Body
    Vtb_moment6_stream___024root___eval_initial__TOP__0(vlSelf);
    Vtb_moment6_stream___024root___eval_initial__TOP__1(vlSelf);
    vlSelf->__Vtrigrprev__TOP__tb_moment6_stream__DOT__clk 
        = vlSelf->tb_moment6_stream__DOT__clk;
}

VL_INLINE_OPT VlCoroutine Vtb_moment6_stream___024root___eval_initial__TOP__1(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___eval_initial__TOP__1\n"); );
    // Body
    while (1U) {
        co_await vlSelf->__VdlySched.delay(5U, "tb_moment6_stream.sv", 
                                           3);
        vlSelf->__Vdlyvval__tb_moment6_stream__DOT__clk__v0 
            = (1U & (~ (IData)(vlSelf->tb_moment6_stream__DOT__clk)));
        vlSelf->__Vdlyvset__tb_moment6_stream__DOT__clk__v0 = 1U;
    }
}

void Vtb_moment6_stream___024root___eval_act(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___eval_act\n"); );
}

VL_INLINE_OPT void Vtb_moment6_stream___024root___nba_sequent__TOP__0(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___nba_sequent__TOP__0\n"); );
    // Init
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__accum = 0;
    QData/*47:0*/ __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__accum = 0;
    // Body
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__accum;
    __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__accum 
        = vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__accum;
    if (vlSelf->tb_moment6_stream__DOT__rst_n) {
        if (vlSelf->tb_moment6_stream__DOT__valid_i) {
            if (vlSelf->tb_moment6_stream__DOT__start_i) {
                vlSelf->tb_moment6_stream__DOT__dut__DOT__count_q = 1U;
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__x_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__x_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__x_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__x_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__x_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__x_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__product_ext);
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                    = (0xffffffffffffULL & vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__product_ext);
            } else {
                vlSelf->tb_moment6_stream__DOT__dut__DOT__count_q 
                    = (0xffffU & ((IData)(1U) + (IData)(vlSelf->tb_moment6_stream__DOT__dut__DOT__count_q)));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__x_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__x_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__x_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__x_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__x_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__x_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__product_ext));
                __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                    = (0xffffffffffffULL & (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                            + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__product_ext));
            }
            if (vlSelf->tb_moment6_stream__DOT__last_i) {
                vlSelf->tb_moment6_stream__DOT__sums_o[0U] 
                    = (IData)((0xffffffffffffULL & 
                               ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                 ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__x_ext
                                 : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__accum 
                                    + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__x_ext))));
                vlSelf->tb_moment6_stream__DOT__sums_o[1U] 
                    = ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__sums_o[1U]) 
                       | (IData)(((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__x_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__x_ext))) 
                                  >> 0x20U)));
                vlSelf->tb_moment6_stream__DOT__sums_o[1U] 
                    = ((0xffffU & vlSelf->tb_moment6_stream__DOT__sums_o[1U]) 
                       | ((IData)((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__x_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__x_ext)))) 
                          << 0x10U));
                vlSelf->tb_moment6_stream__DOT__sums_o[2U] 
                    = (((IData)((0xffffffffffffULL 
                                 & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                     ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__x_ext
                                     : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__accum 
                                        + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__x_ext)))) 
                        >> 0x10U) | ((IData)(((0xffffffffffffULL 
                                               & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                                   ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__x_ext
                                                   : 
                                                  (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__accum 
                                                   + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__x_ext))) 
                                              >> 0x20U)) 
                                     << 0x10U));
                vlSelf->tb_moment6_stream__DOT__sums_o[3U] 
                    = (IData)((0xffffffffffffULL & 
                               ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                 ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__x_ext
                                 : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__accum 
                                    + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__x_ext))));
                vlSelf->tb_moment6_stream__DOT__sums_o[4U] 
                    = ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__sums_o[4U]) 
                       | (IData)(((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__x_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__x_ext))) 
                                  >> 0x20U)));
                vlSelf->tb_moment6_stream__DOT__sums_o[4U] 
                    = ((0xffffU & vlSelf->tb_moment6_stream__DOT__sums_o[4U]) 
                       | ((IData)((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__x_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__x_ext)))) 
                          << 0x10U));
                vlSelf->tb_moment6_stream__DOT__sums_o[5U] 
                    = (((IData)((0xffffffffffffULL 
                                 & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                     ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__x_ext
                                     : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__accum 
                                        + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__x_ext)))) 
                        >> 0x10U) | ((IData)(((0xffffffffffffULL 
                                               & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                                   ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__x_ext
                                                   : 
                                                  (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__accum 
                                                   + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__x_ext))) 
                                              >> 0x20U)) 
                                     << 0x10U));
                vlSelf->tb_moment6_stream__DOT__sums_o[6U] 
                    = (IData)((0xffffffffffffULL & 
                               ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                 ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__x_ext
                                 : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__accum 
                                    + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__x_ext))));
                vlSelf->tb_moment6_stream__DOT__sums_o[7U] 
                    = ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__sums_o[7U]) 
                       | (IData)(((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__x_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__x_ext))) 
                                  >> 0x20U)));
                vlSelf->tb_moment6_stream__DOT__sums_o[7U] 
                    = ((0xffffU & vlSelf->tb_moment6_stream__DOT__sums_o[7U]) 
                       | ((IData)((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__x_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__x_ext)))) 
                          << 0x10U));
                vlSelf->tb_moment6_stream__DOT__sums_o[8U] 
                    = (((IData)((0xffffffffffffULL 
                                 & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                     ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__x_ext
                                     : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__accum 
                                        + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__x_ext)))) 
                        >> 0x10U) | ((IData)(((0xffffffffffffULL 
                                               & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                                   ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__x_ext
                                                   : 
                                                  (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__accum 
                                                   + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__x_ext))) 
                                              >> 0x20U)) 
                                     << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[0U] 
                    = (IData)((0xffffffffffffULL & 
                               ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                 ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__product_ext
                                 : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__accum 
                                    + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__product_ext))));
                vlSelf->tb_moment6_stream__DOT__cross_o[1U] 
                    = ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[1U]) 
                       | (IData)(((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__product_ext))) 
                                  >> 0x20U)));
                vlSelf->tb_moment6_stream__DOT__cross_o[1U] 
                    = ((0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[1U]) 
                       | ((IData)((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__product_ext)))) 
                          << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[2U] 
                    = (((IData)((0xffffffffffffULL 
                                 & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                     ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__product_ext
                                     : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__accum 
                                        + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__product_ext)))) 
                        >> 0x10U) | ((IData)(((0xffffffffffffULL 
                                               & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                                   ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__product_ext
                                                   : 
                                                  (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__accum 
                                                   + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__product_ext))) 
                                              >> 0x20U)) 
                                     << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[3U] 
                    = (IData)((0xffffffffffffULL & 
                               ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                 ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__product_ext
                                 : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__accum 
                                    + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__product_ext))));
                vlSelf->tb_moment6_stream__DOT__cross_o[4U] 
                    = ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[4U]) 
                       | (IData)(((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__product_ext))) 
                                  >> 0x20U)));
                vlSelf->tb_moment6_stream__DOT__cross_o[4U] 
                    = ((0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[4U]) 
                       | ((IData)((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__product_ext)))) 
                          << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[5U] 
                    = (((IData)((0xffffffffffffULL 
                                 & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                     ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__product_ext
                                     : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                                        + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__product_ext)))) 
                        >> 0x10U) | ((IData)(((0xffffffffffffULL 
                                               & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                                   ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__product_ext
                                                   : 
                                                  (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                                                   + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__product_ext))) 
                                              >> 0x20U)) 
                                     << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[6U] 
                    = (IData)((0xffffffffffffULL & 
                               ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                 ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__product_ext
                                 : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                                    + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__product_ext))));
                vlSelf->tb_moment6_stream__DOT__cross_o[7U] 
                    = ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[7U]) 
                       | (IData)(((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__product_ext))) 
                                  >> 0x20U)));
                vlSelf->tb_moment6_stream__DOT__cross_o[7U] 
                    = ((0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[7U]) 
                       | ((IData)((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__product_ext)))) 
                          << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[8U] 
                    = (((IData)((0xffffffffffffULL 
                                 & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                     ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__product_ext
                                     : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                        + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__product_ext)))) 
                        >> 0x10U) | ((IData)(((0xffffffffffffULL 
                                               & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                                   ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__product_ext
                                                   : 
                                                  (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                                   + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__product_ext))) 
                                              >> 0x20U)) 
                                     << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[9U] 
                    = (IData)((0xffffffffffffULL & 
                               ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                 ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__product_ext
                                 : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__accum 
                                    + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__product_ext))));
                vlSelf->tb_moment6_stream__DOT__cross_o[0xaU] 
                    = ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[0xaU]) 
                       | (IData)(((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__product_ext))) 
                                  >> 0x20U)));
                vlSelf->tb_moment6_stream__DOT__cross_o[0xaU] 
                    = ((0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[0xaU]) 
                       | ((IData)((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__product_ext)))) 
                          << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[0xbU] 
                    = (((IData)((0xffffffffffffULL 
                                 & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                     ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__product_ext
                                     : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__accum 
                                        + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__product_ext)))) 
                        >> 0x10U) | ((IData)(((0xffffffffffffULL 
                                               & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                                   ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__product_ext
                                                   : 
                                                  (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__accum 
                                                   + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__product_ext))) 
                                              >> 0x20U)) 
                                     << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[0xcU] 
                    = (IData)((0xffffffffffffULL & 
                               ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                 ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__product_ext
                                 : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                                    + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__product_ext))));
                vlSelf->tb_moment6_stream__DOT__cross_o[0xdU] 
                    = ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[0xdU]) 
                       | (IData)(((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__product_ext))) 
                                  >> 0x20U)));
                vlSelf->tb_moment6_stream__DOT__cross_o[0xdU] 
                    = ((0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[0xdU]) 
                       | ((IData)((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__product_ext)))) 
                          << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[0xeU] 
                    = (((IData)((0xffffffffffffULL 
                                 & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                     ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__product_ext
                                     : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                                        + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__product_ext)))) 
                        >> 0x10U) | ((IData)(((0xffffffffffffULL 
                                               & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                                   ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__product_ext
                                                   : 
                                                  (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                                                   + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__product_ext))) 
                                              >> 0x20U)) 
                                     << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[0xfU] 
                    = (IData)((0xffffffffffffULL & 
                               ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                 ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__product_ext
                                 : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                    + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__product_ext))));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x10U] 
                    = ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[0x10U]) 
                       | (IData)(((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__product_ext))) 
                                  >> 0x20U)));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x10U] 
                    = ((0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[0x10U]) 
                       | ((IData)((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__product_ext)))) 
                          << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x11U] 
                    = (((IData)((0xffffffffffffULL 
                                 & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                     ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__product_ext
                                     : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__accum 
                                        + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__product_ext)))) 
                        >> 0x10U) | ((IData)(((0xffffffffffffULL 
                                               & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                                   ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__product_ext
                                                   : 
                                                  (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__accum 
                                                   + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__product_ext))) 
                                              >> 0x20U)) 
                                     << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x12U] 
                    = (IData)((0xffffffffffffULL & 
                               ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                 ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__product_ext
                                 : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                                    + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__product_ext))));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x13U] 
                    = ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[0x13U]) 
                       | (IData)(((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__product_ext))) 
                                  >> 0x20U)));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x13U] 
                    = ((0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[0x13U]) 
                       | ((IData)((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__product_ext)))) 
                          << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x14U] 
                    = (((IData)((0xffffffffffffULL 
                                 & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                     ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__product_ext
                                     : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                                        + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__product_ext)))) 
                        >> 0x10U) | ((IData)(((0xffffffffffffULL 
                                               & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                                   ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__product_ext
                                                   : 
                                                  (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                                                   + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__product_ext))) 
                                              >> 0x20U)) 
                                     << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x15U] 
                    = (IData)((0xffffffffffffULL & 
                               ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                 ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__product_ext
                                 : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                    + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__product_ext))));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x16U] 
                    = ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[0x16U]) 
                       | (IData)(((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__product_ext))) 
                                  >> 0x20U)));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x16U] 
                    = ((0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[0x16U]) 
                       | ((IData)((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__product_ext)))) 
                          << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x17U] 
                    = (((IData)((0xffffffffffffULL 
                                 & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                     ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__product_ext
                                     : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                                        + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__product_ext)))) 
                        >> 0x10U) | ((IData)(((0xffffffffffffULL 
                                               & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                                   ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__product_ext
                                                   : 
                                                  (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__accum 
                                                   + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__product_ext))) 
                                              >> 0x20U)) 
                                     << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x18U] 
                    = (IData)((0xffffffffffffULL & 
                               ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                 ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__product_ext
                                 : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                                    + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__product_ext))));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x19U] 
                    = ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[0x19U]) 
                       | (IData)(((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__product_ext))) 
                                  >> 0x20U)));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x19U] 
                    = ((0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[0x19U]) 
                       | ((IData)((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__product_ext)))) 
                          << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x1aU] 
                    = (((IData)((0xffffffffffffULL 
                                 & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                     ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__product_ext
                                     : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                        + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__product_ext)))) 
                        >> 0x10U) | ((IData)(((0xffffffffffffULL 
                                               & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                                   ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__product_ext
                                                   : 
                                                  (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                                   + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__product_ext))) 
                                              >> 0x20U)) 
                                     << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x1bU] 
                    = (IData)((0xffffffffffffULL & 
                               ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                 ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__product_ext
                                 : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                                    + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__product_ext))));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x1cU] 
                    = ((0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[0x1cU]) 
                       | (IData)(((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__product_ext))) 
                                  >> 0x20U)));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x1cU] 
                    = ((0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[0x1cU]) 
                       | ((IData)((0xffffffffffffULL 
                                   & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                       ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__product_ext
                                       : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                          + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__product_ext)))) 
                          << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x1dU] 
                    = (((IData)((0xffffffffffffULL 
                                 & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                     ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__product_ext
                                     : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                        + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__product_ext)))) 
                        >> 0x10U) | ((IData)(((0xffffffffffffULL 
                                               & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                                   ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__product_ext
                                                   : 
                                                  (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                                   + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__product_ext))) 
                                              >> 0x20U)) 
                                     << 0x10U));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x1eU] 
                    = (IData)((0xffffffffffffULL & 
                               ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                 ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__product_ext
                                 : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                    + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__product_ext))));
                vlSelf->tb_moment6_stream__DOT__cross_o[0x1fU] 
                    = (0xffffU & (IData)(((0xffffffffffffULL 
                                           & ((IData)(vlSelf->tb_moment6_stream__DOT__start_i)
                                               ? vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__product_ext
                                               : (vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__accum 
                                                  + vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__product_ext))) 
                                          >> 0x20U)));
                vlSelf->tb_moment6_stream__DOT__result_valid_o = 1U;
            } else {
                vlSelf->tb_moment6_stream__DOT__result_valid_o = 0U;
            }
        } else {
            vlSelf->tb_moment6_stream__DOT__result_valid_o = 0U;
        }
    } else {
        vlSelf->tb_moment6_stream__DOT__dut__DOT__count_q = 0U;
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__sums_o[0U] = 0U;
        vlSelf->tb_moment6_stream__DOT__sums_o[1U] 
            = (0xffff0000U & vlSelf->tb_moment6_stream__DOT__sums_o[1U]);
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__sums_o[1U] 
            = (0xffffU & vlSelf->tb_moment6_stream__DOT__sums_o[1U]);
        vlSelf->tb_moment6_stream__DOT__sums_o[2U] = 0U;
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__sums_o[3U] = 0U;
        vlSelf->tb_moment6_stream__DOT__sums_o[4U] 
            = (0xffff0000U & vlSelf->tb_moment6_stream__DOT__sums_o[4U]);
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__sums_o[4U] 
            = (0xffffU & vlSelf->tb_moment6_stream__DOT__sums_o[4U]);
        vlSelf->tb_moment6_stream__DOT__sums_o[5U] = 0U;
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__sums_o[6U] = 0U;
        vlSelf->tb_moment6_stream__DOT__sums_o[7U] 
            = (0xffff0000U & vlSelf->tb_moment6_stream__DOT__sums_o[7U]);
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__sums_o[7U] 
            = (0xffffU & vlSelf->tb_moment6_stream__DOT__sums_o[7U]);
        vlSelf->tb_moment6_stream__DOT__sums_o[8U] = 0U;
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[0U] = 0U;
        vlSelf->tb_moment6_stream__DOT__cross_o[1U] 
            = (0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[1U]);
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[1U] 
            = (0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[1U]);
        vlSelf->tb_moment6_stream__DOT__cross_o[2U] = 0U;
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[3U] = 0U;
        vlSelf->tb_moment6_stream__DOT__cross_o[4U] 
            = (0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[4U]);
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[4U] 
            = (0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[4U]);
        vlSelf->tb_moment6_stream__DOT__cross_o[5U] = 0U;
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[6U] = 0U;
        vlSelf->tb_moment6_stream__DOT__cross_o[7U] 
            = (0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[7U]);
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[7U] 
            = (0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[7U]);
        vlSelf->tb_moment6_stream__DOT__cross_o[8U] = 0U;
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[9U] = 0U;
        vlSelf->tb_moment6_stream__DOT__cross_o[0xaU] 
            = (0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[0xaU]);
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[0xaU] 
            = (0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[0xaU]);
        vlSelf->tb_moment6_stream__DOT__cross_o[0xbU] = 0U;
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[0xcU] = 0U;
        vlSelf->tb_moment6_stream__DOT__cross_o[0xdU] 
            = (0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[0xdU]);
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[0xdU] 
            = (0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[0xdU]);
        vlSelf->tb_moment6_stream__DOT__cross_o[0xeU] = 0U;
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[0xfU] = 0U;
        vlSelf->tb_moment6_stream__DOT__cross_o[0x10U] 
            = (0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[0x10U]);
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[0x10U] 
            = (0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[0x10U]);
        vlSelf->tb_moment6_stream__DOT__cross_o[0x11U] = 0U;
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[0x12U] = 0U;
        vlSelf->tb_moment6_stream__DOT__cross_o[0x13U] 
            = (0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[0x13U]);
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[0x13U] 
            = (0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[0x13U]);
        vlSelf->tb_moment6_stream__DOT__cross_o[0x14U] = 0U;
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[0x15U] = 0U;
        vlSelf->tb_moment6_stream__DOT__cross_o[0x16U] 
            = (0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[0x16U]);
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[0x16U] 
            = (0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[0x16U]);
        vlSelf->tb_moment6_stream__DOT__cross_o[0x17U] = 0U;
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[0x18U] = 0U;
        vlSelf->tb_moment6_stream__DOT__cross_o[0x19U] 
            = (0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[0x19U]);
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[0x19U] 
            = (0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[0x19U]);
        vlSelf->tb_moment6_stream__DOT__cross_o[0x1aU] = 0U;
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[0x1bU] = 0U;
        vlSelf->tb_moment6_stream__DOT__cross_o[0x1cU] 
            = (0xffff0000U & vlSelf->tb_moment6_stream__DOT__cross_o[0x1cU]);
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[0x1cU] 
            = (0xffffU & vlSelf->tb_moment6_stream__DOT__cross_o[0x1cU]);
        vlSelf->tb_moment6_stream__DOT__cross_o[0x1dU] = 0U;
        __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__accum = 0ULL;
        vlSelf->tb_moment6_stream__DOT__cross_o[0x1eU] = 0U;
        vlSelf->tb_moment6_stream__DOT__cross_o[0x1fU] = 0U;
        vlSelf->tb_moment6_stream__DOT__result_valid_o = 0U;
    }
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__accum;
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__accum 
        = __Vdly__tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__accum;
}

VL_INLINE_OPT void Vtb_moment6_stream___024root___nba_sequent__TOP__1(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___nba_sequent__TOP__1\n"); );
    // Body
    if (vlSelf->__Vdlyvset__tb_moment6_stream__DOT__clk__v0) {
        vlSelf->tb_moment6_stream__DOT__clk = vlSelf->__Vdlyvval__tb_moment6_stream__DOT__clk__v0;
        vlSelf->__Vdlyvset__tb_moment6_stream__DOT__clk__v0 = 0U;
    }
}

void Vtb_moment6_stream___024root___eval_nba(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___eval_nba\n"); );
    // Body
    if (vlSelf->__VnbaTriggered.at(0U)) {
        Vtb_moment6_stream___024root___nba_sequent__TOP__0(vlSelf);
    }
    if (vlSelf->__VnbaTriggered.at(1U)) {
        Vtb_moment6_stream___024root___nba_sequent__TOP__1(vlSelf);
    }
}

void Vtb_moment6_stream___024root___eval_triggers__act(Vtb_moment6_stream___024root* vlSelf);
void Vtb_moment6_stream___024root___timing_commit(Vtb_moment6_stream___024root* vlSelf);
#ifdef VL_DEBUG
VL_ATTR_COLD void Vtb_moment6_stream___024root___dump_triggers__act(Vtb_moment6_stream___024root* vlSelf);
#endif  // VL_DEBUG
void Vtb_moment6_stream___024root___timing_resume(Vtb_moment6_stream___024root* vlSelf);
#ifdef VL_DEBUG
VL_ATTR_COLD void Vtb_moment6_stream___024root___dump_triggers__nba(Vtb_moment6_stream___024root* vlSelf);
#endif  // VL_DEBUG

void Vtb_moment6_stream___024root___eval(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___eval\n"); );
    // Init
    VlTriggerVec<3> __VpreTriggered;
    IData/*31:0*/ __VnbaIterCount;
    CData/*0:0*/ __VnbaContinue;
    // Body
    __VnbaIterCount = 0U;
    __VnbaContinue = 1U;
    while (__VnbaContinue) {
        __VnbaContinue = 0U;
        vlSelf->__VnbaTriggered.clear();
        vlSelf->__VactIterCount = 0U;
        vlSelf->__VactContinue = 1U;
        while (vlSelf->__VactContinue) {
            vlSelf->__VactContinue = 0U;
            Vtb_moment6_stream___024root___eval_triggers__act(vlSelf);
            Vtb_moment6_stream___024root___timing_commit(vlSelf);
            if (vlSelf->__VactTriggered.any()) {
                vlSelf->__VactContinue = 1U;
                if (VL_UNLIKELY((0x64U < vlSelf->__VactIterCount))) {
#ifdef VL_DEBUG
                    Vtb_moment6_stream___024root___dump_triggers__act(vlSelf);
#endif
                    VL_FATAL_MT("tb_moment6_stream.sv", 1, "", "Active region did not converge.");
                }
                vlSelf->__VactIterCount = ((IData)(1U) 
                                           + vlSelf->__VactIterCount);
                __VpreTriggered.andNot(vlSelf->__VactTriggered, vlSelf->__VnbaTriggered);
                vlSelf->__VnbaTriggered.set(vlSelf->__VactTriggered);
                Vtb_moment6_stream___024root___timing_resume(vlSelf);
                Vtb_moment6_stream___024root___eval_act(vlSelf);
            }
        }
        if (vlSelf->__VnbaTriggered.any()) {
            __VnbaContinue = 1U;
            if (VL_UNLIKELY((0x64U < __VnbaIterCount))) {
#ifdef VL_DEBUG
                Vtb_moment6_stream___024root___dump_triggers__nba(vlSelf);
#endif
                VL_FATAL_MT("tb_moment6_stream.sv", 1, "", "NBA region did not converge.");
            }
            __VnbaIterCount = ((IData)(1U) + __VnbaIterCount);
            Vtb_moment6_stream___024root___eval_nba(vlSelf);
        }
    }
}

void Vtb_moment6_stream___024root___timing_commit(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___timing_commit\n"); );
    // Body
    if ((1U & (~ (IData)(vlSelf->__VactTriggered.at(2U))))) {
        vlSelf->__VtrigSched_hd18aefb6__0.commit("@(negedge tb_moment6_stream.clk)");
    }
    if ((1U & (~ (IData)(vlSelf->__VactTriggered.at(0U))))) {
        vlSelf->__VtrigSched_hd18aeef7__0.commit("@(posedge tb_moment6_stream.clk)");
    }
}

void Vtb_moment6_stream___024root___timing_resume(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___timing_resume\n"); );
    // Body
    if (vlSelf->__VactTriggered.at(2U)) {
        vlSelf->__VtrigSched_hd18aefb6__0.resume("@(negedge tb_moment6_stream.clk)");
    }
    if (vlSelf->__VactTriggered.at(0U)) {
        vlSelf->__VtrigSched_hd18aeef7__0.resume("@(posedge tb_moment6_stream.clk)");
    }
    if (vlSelf->__VactTriggered.at(1U)) {
        vlSelf->__VdlySched.resume();
    }
}

#ifdef VL_DEBUG
void Vtb_moment6_stream___024root___eval_debug_assertions(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___eval_debug_assertions\n"); );
}
#endif  // VL_DEBUG
