"""Exercise generated HLS RTL; keep launch failures and numeric checks separate."""
import json
import hashlib
import re
import subprocess
from pathlib import Path
from tool_environment import prepare, link_file

HERE = Path(__file__).resolve().parent


def main():
    root = Path("D:/vivado/Vitis_HLS/2023.1")
    executable, environment = prepare(root)
    out = HERE/"build/hls"
    sim = out/"mlp/solution/sim"
    for directory in (sim/"wrapc", sim/"wrapc_pc"):
        directory.mkdir(parents=True, exist_ok=True)
        for dll in list(executable.parent.glob("*.dll"))+list((root/"tps/win64/msys64/mingw64/bin").glob("*.dll")):
            link_file(dll, directory/dll.name)
    script = out/"cosim.tcl"
    script.write_text('''rename exec z20_original_exec
proc exec {args} {
    foreach arg $args {
        if {[string match *cosim.tv.exe* $arg] || [string match *cosim.pc.exe* $arg]} {
            foreach pattern [list "$::env(XILINX_HLS)/lib/win64.o/*.dll" "$::env(AP_GCC_PATH)/*.dll"] {
                foreach dll [glob -nocomplain $pattern] {
                    set target [file join [pwd] [file tail $dll]]
                    if {![file exists $target]} { file copy $dll $target }
                }
            }
        }
    }
    return [uplevel 1 [list z20_original_exec {*}$args]]
}
open_project mlp
open_solution solution
cosim_design -rtl verilog -tool xsim -ldflags {-static-libgcc -static-libstdc++}
exit
''')
    def run(command, cwd, env, log):
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, errors="replace")
        (out/log).write_text(result.stdout+result.stderr, encoding="utf-8")
        return result
    initial = run([str(executable), "-f", str(script)], out, environment, "cosim-console.txt")
    passed = initial.returncode == 0 and "PASS: shared D->32->3" in initial.stdout
    fallback = False
    simulator_exit = None
    generated = sim/"verilog/run_xsim.bat"
    if not passed and generated.exists():
        fallback = True
        vivado_exe, vivado_env = prepare(root.parents[1]/"Vivado"/root.name)
        for tool, args in [("xelab", ["xil_defaultlib.apatb_z20_mlp_top", "glbl", "-Oenable_linking_all_libraries",
                "-prj", "z20_mlp.prj", "-L", "xil_defaultlib", "-L", "unisims_ver", "-L", "xpm", "-s", "z20_mlp"]),
                ("xsim", ["--noieeewarnings", "z20_mlp", "-tclbatch", "z20_mlp.tcl"])]:
            if tool == "xsim":
                for dll in vivado_exe.parent.glob("*.dll"):
                    link_file(dll, sim/"verilog/xsim.dir/z20_mlp"/dll.name)
            result = run([str(vivado_exe.parent/(tool+".exe")), *args], sim/"verilog", vivado_env, tool+"-direct.txt")
            completed = (tool == "xsim" and "6 / 6" in result.stdout and "$finish called" in result.stdout)
            if tool == "xsim":
                simulator_exit = result.returncode
            if (result.returncode and not completed) or re.search(r"(?im)^\s*(?:ERROR:|Fatal:)", result.stdout):
                break
        else:
            for dll in list(executable.parent.glob("*.dll"))+list((root/"tps/win64/msys64/mingw64/bin").glob("*.dll")):
                link_file(dll, sim/"wrapc_pc"/dll.name)
            result = run([str(sim/"wrapc_pc/cosim.pc.exe")], sim/"wrapc_pc", environment, "postcheck-direct.txt")
            passed = result.returncode == 0 and "PASS: shared D->32->3" in result.stdout
    report = dict(passed=passed, initial_exit=initial.returncode, direct_generated_commands=fallback,
                  simulator_exit=simulator_exit, tool_exit_clean=simulator_exit == 0,
                  board_executed=False, transactions=6 if passed else None,
                  sources={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in (HERE/"hardware/hls").glob("*") if p.is_file()})
    (out/"cosim-result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return int(not passed)


if __name__ == "__main__": raise SystemExit(main())
