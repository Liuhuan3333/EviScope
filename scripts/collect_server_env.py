#!/usr/bin/env python3
"""Collect a deliberately non-identifying, non-secret server inventory."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def run(argv: list[str]) -> str | None:
    if shutil.which(argv[0]) is None:
        return None
    try:
        result = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env={"PATH": os.environ.get("PATH", "")},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def first_line(command: list[str]) -> str | None:
    value = run(command)
    return value.splitlines()[0] if value else None


def cpu_model_summary() -> str | None:
    """Return only the CPU model, never the full host inventory."""
    if platform.system() == "Darwin":
        return first_line(["sysctl", "-n", "machdep.cpu.brand_string"])
    if platform.system() == "Linux":
        try:
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace").splitlines():
                if line.lower().startswith("model name") and ":" in line:
                    return line.split(":", 1)[1].strip() or None
        except OSError:
            pass
    return platform.processor() or None


def total_memory_bytes() -> int | None:
    """Collect aggregate RAM capacity without invoking identity-bearing tools."""
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        return None
    if isinstance(page_size, int) and isinstance(page_count, int):
        return page_size * page_count
    return None


def gpu_inventory() -> list[dict[str, str]]:
    query = run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version,compute_cap",
            "--format=csv,noheader,nounits",
        ]
    )
    if not query:
        return []
    gpus = []
    for line in query.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) == 4:
            gpus.append(
                {
                    "name": fields[0],
                    "memory_mib": fields[1],
                    "driver_version": fields[2],
                    "compute_capability": fields[3],
                }
            )
    return gpus


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    data = {
        "schema_version": "eviscope.server-environment.v0.1",
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "cpu": {
            "logical_count": os.cpu_count(),
            "model_summary": cpu_model_summary(),
        },
        "memory": {"total_bytes": total_memory_bytes()},
        "gpus": gpu_inventory(),
        "tools": {
            "python": platform.python_version(),
            "git": first_line(["git", "--version"]),
            "docker": first_line(["docker", "--version"]),
            "podman": first_line(["podman", "--version"]),
            "nvidia_smi": first_line(["nvidia-smi", "--version"]),
        },
        "scheduler": {
            "slurm": first_line(["sinfo", "--version"]),
            "pbs": first_line(["qstat", "--version"]),
        },
        "secret_policy": "no environment values, credentials, usernames, hostnames, IPs, SSH config, or process command lines collected",
    }
    args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
