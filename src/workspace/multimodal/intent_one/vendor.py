"""Single import adapter for the frozen, provenance-checked baseline."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
def setup():
    for name in ('eye','runtime','eeg_apps_z15','media',''):
        path=str(ROOT/'vendor'/name)
        if path not in sys.path:sys.path.append(path)

setup()
