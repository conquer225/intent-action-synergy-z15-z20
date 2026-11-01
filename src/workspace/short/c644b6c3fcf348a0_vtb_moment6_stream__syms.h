// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Symbol table internal header
//
// Internal details; most calling programs do not need this header,
// unless using verilator public meta comments.

#ifndef VERILATED_VTB_MOMENT6_STREAM__SYMS_H_
#define VERILATED_VTB_MOMENT6_STREAM__SYMS_H_  // guard

#include "verilated.h"

// INCLUDE MODEL CLASS

#include "Vtb_moment6_stream.h"

// INCLUDE MODULE CLASSES
#include "Vtb_moment6_stream___024root.h"

// SYMS CLASS (contains all model state)
class Vtb_moment6_stream__Syms final : public VerilatedSyms {
  public:
    // INTERNAL STATE
    Vtb_moment6_stream* const __Vm_modelp;
    bool __Vm_didInit = false;

    // MODULE INSTANCE STATE
    Vtb_moment6_stream___024root   TOP;

    // SCOPE NAMES
    VerilatedScope __Vscope_tb_moment6_stream;
    VerilatedScope __Vscope_tb_moment6_stream__send;
    VerilatedScope __Vscope_tb_moment6_stream__unnamedblk2;

    // CONSTRUCTORS
    Vtb_moment6_stream__Syms(VerilatedContext* contextp, const char* namep, Vtb_moment6_stream* modelp);
    ~Vtb_moment6_stream__Syms();

    // METHODS
    const char* name() { return TOP.name(); }
} VL_ATTR_ALIGNED(VL_CACHE_LINE_BYTES);

#endif  // guard
