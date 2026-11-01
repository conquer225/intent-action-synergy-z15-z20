"""Apply child-only limits before executing the existing native decoder."""
import os
from pathlib import Path
import resource
import sys

if len(sys.argv) != 3:
    raise SystemExit(2)
decoder, video = [Path(value).resolve(strict=True) for value in sys.argv[1:]]
if not decoder.is_file() or not video.is_file() or video.suffix != ".mp4":
    raise SystemExit(2)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
resource.setrlimit(resource.RLIMIT_CPU, (25, 26))
resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 ** 2, 384 * 1024 ** 2))
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
os.nice(8)
os.execv(str(decoder), [str(decoder), str(video), "bgr", "1"])
