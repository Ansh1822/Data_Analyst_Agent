"""Section 2 - Sandbox. Runs LLM-written Python away from the API process.

Layers of protection:
  1. Static check: reject obviously dangerous code before running it.
  2. Process isolation: separate process, timeout, minimal environment (no API key).
  3. Docker mode: no network, memory/CPU/PID limits, only the run folder mounted.
"""
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import SANDBOX_IMAGE, SANDBOX_MODE, SANDBOX_TIMEOUT

# Everything the generated script can rely on. `df` is the uploaded CSV.
PRELUDE = '''import warnings
warnings.filterwarnings("ignore")
import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import duckdb
df = pd.read_csv("data.csv")
'''

BLOCKED_PATTERNS = [
    (r"\b(import|from)\s+(os|sys|subprocess|socket|shutil|requests|urllib|http|ftplib|ctypes|pickle|importlib|builtins)\b", "importing system/network modules"),
    (r"\b(eval|exec|compile|__import__|open|input)\s*\(", "eval/exec/open/input calls"),
    (r"\bto_(csv|excel|pickle|parquet|json|sql)\s*\(", "writing data files"),
    (r"\bread_(csv|excel|sql|parquet)\s*\(", "re-reading data (df is already loaded)"),
]


@dataclass
class ExecResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    charts: list = field(default_factory=list)
    seconds: float = 0.0


def check_code(code: str):
    for pattern, reason in BLOCKED_PATTERNS:
        if re.search(pattern, code):
            return reason
    return None


def run_code(run_dir: Path, code: str, tag: str) -> ExecResult:
    violation = check_code(code)
    if violation:
        return ExecResult(False, stderr=f"SafetyError: blocked by sandbox ({violation}). Use the preloaded `df` and only pandas/numpy/matplotlib/seaborn/duckdb.")

    charts_dir = run_dir / "charts"
    charts_dir.mkdir(exist_ok=True)
    before = {p.name for p in charts_dir.glob("*.png")}

    script = run_dir / f"{tag}.py"
    script.write_text(PRELUDE + "\n" + code + "\n", encoding="utf-8")

    if SANDBOX_MODE == "docker":
        cmd = ["docker", "run", "--rm", "--network", "none", "--memory", "512m", "--cpus", "1",
               "--pids-limit", "128", "--read-only", "--tmpfs", "/tmp",
               "-v", f"{run_dir.resolve()}:/work", "-w", "/work", SANDBOX_IMAGE, "python", script.name]
    else:
        cmd = [sys.executable, script.name]

    # Minimal environment so generated code never sees GROQ_API_KEY or other secrets.
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),  # required by Python on Windows
        "MPLBACKEND": "Agg",
        "MPLCONFIGDIR": str(run_dir / ".mpl"),
        "PYTHONIOENCODING": "utf-8",
    }

    start = time.time()
    try:
        proc = subprocess.run(cmd, cwd=run_dir, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=SANDBOX_TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        return ExecResult(False, stderr=f"TimeoutError: script exceeded {SANDBOX_TIMEOUT}s. Use a cheaper approach.", seconds=time.time() - start)
    except FileNotFoundError as e:
        return ExecResult(False, stderr=f"Sandbox could not start: {e}", seconds=time.time() - start)

    new_charts = sorted({p.name for p in charts_dir.glob("*.png")} - before)
    return ExecResult(
        ok=proc.returncode == 0,
        stdout=proc.stdout[-4000:],
        stderr=proc.stderr[-2000:],
        charts=new_charts,
        seconds=round(time.time() - start, 2),
    )
