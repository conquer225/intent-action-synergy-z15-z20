import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def main():
    subprocess.run(["C:/mingw64/mingw64/bin/gcc.exe", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-shared", "-static", "-static-libgcc", "-Itests/include", "-Isrc/app", "src/app/haar.c",
                    "src/app/auto_face.c", "src/app/eye_tracker.c", "src/app/net_protocol.c", "src/app/net_control.c",
                    "tools/board_bridge.c", "-lm", "-o", "tests/board_core.dll"], cwd=ROOT, check=True)
if __name__ == "__main__":
    main()
