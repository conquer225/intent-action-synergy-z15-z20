// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vtb_moment6_stream.h for the primary calling header

#include "verilated.h"

#include "Vtb_moment6_stream__Syms.h"
#include "Vtb_moment6_stream___024root.h"

void Vtb_moment6_stream___024root___ctor_var_reset(Vtb_moment6_stream___024root* vlSelf);

Vtb_moment6_stream___024root::Vtb_moment6_stream___024root(Vtb_moment6_stream__Syms* symsp, const char* v__name)
    : VerilatedModule{v__name}
    , __VdlySched{*symsp->_vm_contextp__}
    , vlSymsp{symsp}
 {
    // Reset structure values
    Vtb_moment6_stream___024root___ctor_var_reset(this);
}

void Vtb_moment6_stream___024root::__Vconfigure(bool first) {
    if (false && first) {}  // Prevent unused
}

Vtb_moment6_stream___024root::~Vtb_moment6_stream___024root() {
}
