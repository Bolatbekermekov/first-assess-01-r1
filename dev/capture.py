"""Dev-only: run one command and record it with its environment, exit code, stdout and stderr in a log file.

Usage: python dev/capture.py LOG -- COMMAND [ARG ...]
"""

import datetime
import platform
import shlex
import subprocess
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    separator = argv.index("--")
    log, command = Path(argv[1]), argv[separator + 1 :]
    started = datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    log.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"$ {shlex.join(command)}\n"
        f"# started_utc: {started}\n"
        f"# cwd: {Path.cwd()}\n"
        f"# python: {sys.version.split()[0]} ({platform.python_implementation()})\n"
        f"# platform: {platform.platform()}\n"
        f"# exit_code: {result.returncode}\n"
    )
    log.write_text(f"{header}## stdout\n{result.stdout}## stderr\n{result.stderr}", encoding="utf-8")
    print(f"{log}: exit {result.returncode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
