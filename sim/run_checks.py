"""Run the bounded offline regression set against a restored workspace."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

SOURCE_TESTS = ("test_npu.py", "test_backend.py", "test_board_target.py", "test_link.py", "test_video.py")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package = Path(__file__).resolve().parents[1]
    workspace, output = args.workspace.resolve(), args.output.resolve()
    try:
        if output.exists():
            raise ValueError("output exists; choose a new external log directory")
        for root in (package, workspace):
            if output.is_relative_to(root):
                raise ValueError("logs must be outside the package and restored workspace")
        z20 = workspace / "integrations/z20_compute"
        if not (z20 / "tests/test_npu.py").is_file():
            raise ValueError("workspace is not the restored Z15 + Z20 source set")
        output.mkdir(parents=True)
        jobs = [("z20_regression", z20, "tests", SOURCE_TESTS),
                ("portable_skill", package / "skill", "tests", ("test_*.py",)),
                ("submission_tools", package, "sim", ("test_*.py",))]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
        # Do not inherit an unrelated checkout's imports.
        env.pop("PYTHONPATH", None)
        results = []
        for name, cwd, directory, patterns in jobs:
            code = "\n".join([
                "import json, sys, unittest",
                "suite = unittest.TestSuite()",
                "for pattern in " + repr(patterns) + ":",
                "    suite.addTests(unittest.defaultTestLoader.discover(" + repr(directory) + ", pattern=pattern))",
                "count = suite.countTestCases()",
                "result = unittest.TextTestRunner(verbosity=2).run(suite)",
                "print(json.dumps({'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped)}))",
                "raise SystemExit(0 if count > 0 and result.wasSuccessful() else 1)",
            ])
            start = time.monotonic()
            run = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", code], cwd=cwd,
                env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
            (output / (name + ".log")).write_text(run.stdout + "\n" + run.stderr, encoding="utf-8")
            counts = {}
            if run.stdout.strip():
                try:
                    counts = json.loads(run.stdout.strip().splitlines()[-1])
                except ValueError:
                    pass
            results.append({"name": name, "exit_code": run.returncode,
                            "duration_seconds": time.monotonic() - start, **counts})
        report = {"passed": all(r["exit_code"] == 0 for r in results),
                  "scope": "offline_software_regression_only", "board_executed": False,
                  "python": sys.version, "platform": platform.platform(),
                  "workspace": str(workspace), "package": str(package), "results": results}
        (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=True, indent=2))
        return 0 if report["passed"] else 1
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"passed": False, "board_executed": False, "error": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
