// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Symbol table implementation internals

#include "Vtb_moment6_stream__Syms.h"
#include "Vtb_moment6_stream.h"
#include "Vtb_moment6_stream___024root.h"

// FUNCTIONS
Vtb_moment6_stream__Syms::~Vtb_moment6_stream__Syms()
{
}

Vtb_moment6_stream__Syms::Vtb_moment6_stream__Syms(VerilatedContext* contextp, const char* namep, Vtb_moment6_stream* modelp)
    : VerilatedSyms{contextp}
    // Setup internal state of the Syms class
    , __Vm_modelp{modelp}
    // Setup module instances
    , TOP{this, namep}
{
    // Configure time unit / time precision
    _vm_contextp__->timeunit(-12);
    _vm_contextp__->timeprecision(-12);
    // Setup each module's pointers to their submodules
    // Setup each module's pointer back to symbol table (for public functions)
    TOP.__Vconfigure(true);
    // Setup scopes
    __Vscope_tb_moment6_stream.configure(this, name(), "tb_moment6_stream", "tb_moment6_stream", -12, VerilatedScope::SCOPE_OTHER);
    __Vscope_tb_moment6_stream__send.configure(this, name(), "tb_moment6_stream.send", "send", -12, VerilatedScope::SCOPE_OTHER);
    __Vscope_tb_moment6_stream__unnamedblk2.configure(this, name(), "tb_moment6_stream.unnamedblk2", "unnamedblk2", -12, VerilatedScope::SCOPE_OTHER);
}
