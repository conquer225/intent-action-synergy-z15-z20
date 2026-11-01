// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vtb_moment6_stream.h for the primary calling header

#include "verilated.h"

#include "Vtb_moment6_stream___024root.h"

VL_ATTR_COLD void Vtb_moment6_stream___024root___eval_static__TOP(Vtb_moment6_stream___024root* vlSelf);

VL_ATTR_COLD void Vtb_moment6_stream___024root___eval_static(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___eval_static\n"); );
    // Body
    Vtb_moment6_stream___024root___eval_static__TOP(vlSelf);
}

VL_ATTR_COLD void Vtb_moment6_stream___024root___eval_static__TOP(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___eval_static__TOP\n"); );
    // Body
    vlSelf->tb_moment6_stream__DOT__clk = 0U;
    vlSelf->tb_moment6_stream__DOT__rst_n = 0U;
    vlSelf->tb_moment6_stream__DOT__valid_i = 0U;
    vlSelf->tb_moment6_stream__DOT__start_i = 0U;
    vlSelf->tb_moment6_stream__DOT__last_i = 0U;
    vlSelf->tb_moment6_stream__DOT__sample_i[0U] = 0U;
    vlSelf->tb_moment6_stream__DOT__sample_i[1U] = 0U;
    vlSelf->tb_moment6_stream__DOT__sample_i[2U] = 0U;
}

VL_ATTR_COLD void Vtb_moment6_stream___024root___eval_final(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___eval_final\n"); );
}

VL_ATTR_COLD void Vtb_moment6_stream___024root___eval_triggers__stl(Vtb_moment6_stream___024root* vlSelf);
#ifdef VL_DEBUG
VL_ATTR_COLD void Vtb_moment6_stream___024root___dump_triggers__stl(Vtb_moment6_stream___024root* vlSelf);
#endif  // VL_DEBUG
VL_ATTR_COLD void Vtb_moment6_stream___024root___eval_stl(Vtb_moment6_stream___024root* vlSelf);

VL_ATTR_COLD void Vtb_moment6_stream___024root___eval_settle(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___eval_settle\n"); );
    // Init
    CData/*0:0*/ __VstlContinue;
    // Body
    vlSelf->__VstlIterCount = 0U;
    __VstlContinue = 1U;
    while (__VstlContinue) {
        __VstlContinue = 0U;
        Vtb_moment6_stream___024root___eval_triggers__stl(vlSelf);
        if (vlSelf->__VstlTriggered.any()) {
            __VstlContinue = 1U;
            if (VL_UNLIKELY((0x64U < vlSelf->__VstlIterCount))) {
#ifdef VL_DEBUG
                Vtb_moment6_stream___024root___dump_triggers__stl(vlSelf);
#endif
                VL_FATAL_MT("tb_moment6_stream.sv", 1, "", "Settle region did not converge.");
            }
            vlSelf->__VstlIterCount = ((IData)(1U) 
                                       + vlSelf->__VstlIterCount);
            Vtb_moment6_stream___024root___eval_stl(vlSelf);
        }
    }
}

#ifdef VL_DEBUG
VL_ATTR_COLD void Vtb_moment6_stream___024root___dump_triggers__stl(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___dump_triggers__stl\n"); );
    // Body
    if ((1U & (~ (IData)(vlSelf->__VstlTriggered.any())))) {
        VL_DBG_MSGF("         No triggers active\n");
    }
    if (vlSelf->__VstlTriggered.at(0U)) {
        VL_DBG_MSGF("         'stl' region trigger index 0 is active: Internal 'stl' trigger - first iteration\n");
    }
}
#endif  // VL_DEBUG

VL_ATTR_COLD void Vtb_moment6_stream___024root___stl_sequent__TOP__0(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___stl_sequent__TOP__0\n"); );
    // Init
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__product = 0;
    IData/*31:0*/ tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__product;
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__product = 0;
    // Body
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__x_ext 
        = (((QData)((IData)((- (IData)((1U & (vlSelf->tb_moment6_stream__DOT__sample_i[0U] 
                                              >> 0xfU)))))) 
            << 0x10U) | (QData)((IData)((0xffffU & 
                                         vlSelf->tb_moment6_stream__DOT__sample_i[0U]))));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__x_ext 
        = (((QData)((IData)((- (IData)((vlSelf->tb_moment6_stream__DOT__sample_i[0U] 
                                        >> 0x1fU))))) 
            << 0x10U) | (QData)((IData)((vlSelf->tb_moment6_stream__DOT__sample_i[0U] 
                                         >> 0x10U))));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__x_ext 
        = (((QData)((IData)((- (IData)((1U & (vlSelf->tb_moment6_stream__DOT__sample_i[1U] 
                                              >> 0xfU)))))) 
            << 0x10U) | (QData)((IData)((0xffffU & 
                                         vlSelf->tb_moment6_stream__DOT__sample_i[1U]))));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__x_ext 
        = (((QData)((IData)((- (IData)((vlSelf->tb_moment6_stream__DOT__sample_i[1U] 
                                        >> 0x1fU))))) 
            << 0x10U) | (QData)((IData)((vlSelf->tb_moment6_stream__DOT__sample_i[1U] 
                                         >> 0x10U))));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__x_ext 
        = (((QData)((IData)((- (IData)((1U & (vlSelf->tb_moment6_stream__DOT__sample_i[2U] 
                                              >> 0xfU)))))) 
            << 0x10U) | (QData)((IData)((0xffffU & 
                                         vlSelf->tb_moment6_stream__DOT__sample_i[2U]))));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__x_ext 
        = (((QData)((IData)((- (IData)((vlSelf->tb_moment6_stream__DOT__sample_i[2U] 
                                        >> 0x1fU))))) 
            << 0x10U) | (QData)((IData)((vlSelf->tb_moment6_stream__DOT__sample_i[2U] 
                                         >> 0x10U))));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (0xffffU 
                                                & vlSelf->tb_moment6_stream__DOT__sample_i[0U])), 
                      VL_EXTENDS_II(32,16, (0xffffU 
                                            & vlSelf->tb_moment6_stream__DOT__sample_i[0U])));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (0xffffU 
                                                & vlSelf->tb_moment6_stream__DOT__sample_i[0U])), 
                      VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[0U] 
                                            >> 0x10U)));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (0xffffU 
                                                & vlSelf->tb_moment6_stream__DOT__sample_i[0U])), 
                      VL_EXTENDS_II(32,16, (0xffffU 
                                            & vlSelf->tb_moment6_stream__DOT__sample_i[1U])));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (0xffffU 
                                                & vlSelf->tb_moment6_stream__DOT__sample_i[0U])), 
                      VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[1U] 
                                            >> 0x10U)));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (0xffffU 
                                                & vlSelf->tb_moment6_stream__DOT__sample_i[0U])), 
                      VL_EXTENDS_II(32,16, (0xffffU 
                                            & vlSelf->tb_moment6_stream__DOT__sample_i[2U])));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (0xffffU 
                                                & vlSelf->tb_moment6_stream__DOT__sample_i[0U])), 
                      VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[2U] 
                                            >> 0x10U)));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[0U] 
                                                >> 0x10U)), 
                      VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[0U] 
                                            >> 0x10U)));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[0U] 
                                                >> 0x10U)), 
                      VL_EXTENDS_II(32,16, (0xffffU 
                                            & vlSelf->tb_moment6_stream__DOT__sample_i[1U])));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[0U] 
                                                >> 0x10U)), 
                      VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[1U] 
                                            >> 0x10U)));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[0U] 
                                                >> 0x10U)), 
                      VL_EXTENDS_II(32,16, (0xffffU 
                                            & vlSelf->tb_moment6_stream__DOT__sample_i[2U])));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[0U] 
                                                >> 0x10U)), 
                      VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[2U] 
                                            >> 0x10U)));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (0xffffU 
                                                & vlSelf->tb_moment6_stream__DOT__sample_i[1U])), 
                      VL_EXTENDS_II(32,16, (0xffffU 
                                            & vlSelf->tb_moment6_stream__DOT__sample_i[1U])));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (0xffffU 
                                                & vlSelf->tb_moment6_stream__DOT__sample_i[1U])), 
                      VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[1U] 
                                            >> 0x10U)));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (0xffffU 
                                                & vlSelf->tb_moment6_stream__DOT__sample_i[1U])), 
                      VL_EXTENDS_II(32,16, (0xffffU 
                                            & vlSelf->tb_moment6_stream__DOT__sample_i[2U])));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (0xffffU 
                                                & vlSelf->tb_moment6_stream__DOT__sample_i[1U])), 
                      VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[2U] 
                                            >> 0x10U)));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[1U] 
                                                >> 0x10U)), 
                      VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[1U] 
                                            >> 0x10U)));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[1U] 
                                                >> 0x10U)), 
                      VL_EXTENDS_II(32,16, (0xffffU 
                                            & vlSelf->tb_moment6_stream__DOT__sample_i[2U])));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[1U] 
                                                >> 0x10U)), 
                      VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[2U] 
                                            >> 0x10U)));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (0xffffU 
                                                & vlSelf->tb_moment6_stream__DOT__sample_i[2U])), 
                      VL_EXTENDS_II(32,16, (0xffffU 
                                            & vlSelf->tb_moment6_stream__DOT__sample_i[2U])));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (0xffffU 
                                                & vlSelf->tb_moment6_stream__DOT__sample_i[2U])), 
                      VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[2U] 
                                            >> 0x10U)));
    tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__product 
        = VL_MULS_III(32, VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[2U] 
                                                >> 0x10U)), 
                      VL_EXTENDS_II(32,16, (vlSelf->tb_moment6_stream__DOT__sample_i[2U] 
                                            >> 0x10U)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__product)));
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__product_ext 
        = (((QData)((IData)((0xffffU & (- (IData)((tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__product 
                                                   >> 0x1fU)))))) 
            << 0x20U) | (QData)((IData)(tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__product)));
}

VL_ATTR_COLD void Vtb_moment6_stream___024root___eval_stl(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___eval_stl\n"); );
    // Body
    if (vlSelf->__VstlTriggered.at(0U)) {
        Vtb_moment6_stream___024root___stl_sequent__TOP__0(vlSelf);
    }
}

#ifdef VL_DEBUG
VL_ATTR_COLD void Vtb_moment6_stream___024root___dump_triggers__act(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___dump_triggers__act\n"); );
    // Body
    if ((1U & (~ (IData)(vlSelf->__VactTriggered.any())))) {
        VL_DBG_MSGF("         No triggers active\n");
    }
    if (vlSelf->__VactTriggered.at(0U)) {
        VL_DBG_MSGF("         'act' region trigger index 0 is active: @(posedge tb_moment6_stream.clk)\n");
    }
    if (vlSelf->__VactTriggered.at(1U)) {
        VL_DBG_MSGF("         'act' region trigger index 1 is active: @([true] __VdlySched.awaitingCurrentTime())\n");
    }
    if (vlSelf->__VactTriggered.at(2U)) {
        VL_DBG_MSGF("         'act' region trigger index 2 is active: @(negedge tb_moment6_stream.clk)\n");
    }
}
#endif  // VL_DEBUG

#ifdef VL_DEBUG
VL_ATTR_COLD void Vtb_moment6_stream___024root___dump_triggers__nba(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___dump_triggers__nba\n"); );
    // Body
    if ((1U & (~ (IData)(vlSelf->__VnbaTriggered.any())))) {
        VL_DBG_MSGF("         No triggers active\n");
    }
    if (vlSelf->__VnbaTriggered.at(0U)) {
        VL_DBG_MSGF("         'nba' region trigger index 0 is active: @(posedge tb_moment6_stream.clk)\n");
    }
    if (vlSelf->__VnbaTriggered.at(1U)) {
        VL_DBG_MSGF("         'nba' region trigger index 1 is active: @([true] __VdlySched.awaitingCurrentTime())\n");
    }
    if (vlSelf->__VnbaTriggered.at(2U)) {
        VL_DBG_MSGF("         'nba' region trigger index 2 is active: @(negedge tb_moment6_stream.clk)\n");
    }
}
#endif  // VL_DEBUG

VL_ATTR_COLD void Vtb_moment6_stream___024root___ctor_var_reset(Vtb_moment6_stream___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vtb_moment6_stream__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtb_moment6_stream___024root___ctor_var_reset\n"); );
    // Body
    vlSelf->tb_moment6_stream__DOT__clk = VL_RAND_RESET_I(1);
    vlSelf->tb_moment6_stream__DOT__rst_n = VL_RAND_RESET_I(1);
    vlSelf->tb_moment6_stream__DOT__valid_i = VL_RAND_RESET_I(1);
    vlSelf->tb_moment6_stream__DOT__start_i = VL_RAND_RESET_I(1);
    vlSelf->tb_moment6_stream__DOT__last_i = VL_RAND_RESET_I(1);
    VL_RAND_RESET_W(96, vlSelf->tb_moment6_stream__DOT__sample_i);
    vlSelf->tb_moment6_stream__DOT__result_valid_o = VL_RAND_RESET_I(1);
    VL_RAND_RESET_W(288, vlSelf->tb_moment6_stream__DOT__sums_o);
    VL_RAND_RESET_W(1008, vlSelf->tb_moment6_stream__DOT__cross_o);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__count_q = VL_RAND_RESET_I(16);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__0__KET____DOT__x_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__1__KET____DOT__x_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__2__KET____DOT__x_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__3__KET____DOT__x_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__4__KET____DOT__x_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_sum__BRA__5__KET____DOT__x_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__0__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__1__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__2__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__3__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__4__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__0__KET____DOT__g_col__BRA__5__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__1__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__2__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__3__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__4__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__1__KET____DOT__g_col__BRA__5__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__2__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__3__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__4__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__2__KET____DOT__g_col__BRA__5__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__3__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__4__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__3__KET____DOT__g_col__BRA__5__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__4__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__4__KET____DOT__g_col__BRA__5__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__accum = VL_RAND_RESET_Q(48);
    vlSelf->tb_moment6_stream__DOT__dut__DOT__g_row__BRA__5__KET____DOT__g_col__BRA__5__KET____DOT__product_ext = VL_RAND_RESET_Q(48);
    vlSelf->__Vdlyvval__tb_moment6_stream__DOT__clk__v0 = VL_RAND_RESET_I(1);
    vlSelf->__Vdlyvset__tb_moment6_stream__DOT__clk__v0 = 0;
    vlSelf->__Vtrigrprev__TOP__tb_moment6_stream__DOT__clk = VL_RAND_RESET_I(1);
}
