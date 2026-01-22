#!/usr/bin/env python3
"""
lxc-gpu-freeze: Freeze/thaw LXC containers with GPU power state management.

Usage:
    lxc-freeze-thaw freeze <lxc_id>              # Freeze LXC, auto-detect GPUs from config
    lxc-freeze-thaw freeze <lxc_id> -g 0         # Freeze LXC, lock GPU 0
    lxc-freeze-thaw freeze <lxc_id> -ng          # Freeze LXC only (no GPU operations)
    lxc-freeze-thaw freeze <lxc_id> -g 0,2,3     # Freeze LXC, lock GPUs 0, 2, 3

Aliases: f/freeze (freeze), t/thaw/u/unfreeze (thaw/unfreeze)
"""

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

FREEZE_ALIASES = ("freeze", "f")
THAW_ALIASES = ("thaw", "t", "unfreeze", "u")


def run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Execute command, optionally raising on failure."""
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def get_cgroup_path(lxc_id: str) -> Path:
    """Return cgroup freeze path for LXC."""
    return Path(f"/sys/fs/cgroup/lxc/{lxc_id}/cgroup.freeze")


def read_cgroup_state(lxc_id: str) -> int:
    """Read current freeze state. Returns 0 (thawed) or 1 (frozen)."""
    cgroup_path = get_cgroup_path(lxc_id)

    if not cgroup_path.exists():
        sys.exit(f"ERR: cgroup path not found: {cgroup_path}")

    return int(cgroup_path.read_text().strip())


def write_cgroup(lxc_id: str, value: str) -> None:
    """Write to cgroup freeze file."""
    cgroup_path = get_cgroup_path(lxc_id)

    if not cgroup_path.exists():
        sys.exit(f"ERR: cgroup path not found: {cgroup_path}")

    cgroup_path.write_text(value)


def detect_gpus_from_config(lxc_id: str) -> list[int]:
    """Parse LXC config to find passthrough GPU indices."""
    config_path = Path(f"/etc/pve/lxc/{lxc_id}.conf")

    if not config_path.exists():
        sys.exit(f"ERR: LXC config not found: {config_path}")

    gpus = set()
    for line in config_path.read_text().splitlines():
        if not re.match(r"^dev\d+:", line):
            continue
        match = re.search(r"/dev/nvidia(\d+)\s*$", line)
        if match:
            gpus.add(int(match.group(1)))

    if not gpus:
        sys.exit(f"ERR: No GPUs found in {config_path}")

    return sorted(gpus)


def parse_gpu_arg(gpu_arg: str, lxc_id: str) -> list[int]:
    """Parse GPU argument into list of indices."""
    if gpu_arg == "auto":
        return detect_gpus_from_config(lxc_id)

    try:
        return [int(g.strip()) for g in gpu_arg.split(",")]
    except ValueError:
        sys.exit(f"ERR: invalid GPU index in '{gpu_arg}'")


def verify_state(lxc_id: str, expected: int, action: str) -> None:
    """Verify cgroup state matches expected. Exit with error if not."""
    actual = read_cgroup_state(lxc_id)

    if actual != expected:
        state_names = {0: "thawed", 1: "frozen"}
        sys.exit(
            f"ERR: {action} failed — expected {state_names[expected]}, "
            f"got {state_names[actual]}"
        )


def reset_gpu_clocks(gpus: list[int]) -> None:
    """Reset GPU memory and graphics clocks to default."""
    for gpu in gpus:
        run_cmd(["nvidia-smi", "-i", str(gpu), "-rmc"])
        run_cmd(["nvidia-smi", "-i", str(gpu), "-rgc"])


def lock_gpu_clocks(gpus: list[int]) -> None:
    """Lock GPU memory and graphics clocks to minimum."""
    for gpu in gpus:
        run_cmd(["nvidia-smi", "-i", str(gpu), "-lmc", "405"])
        run_cmd(["nvidia-smi", "-i", str(gpu), "-lgc", "210,210"])


def freeze(lxc_id: str, gpus: list[int] | None, gpu_explicit: bool) -> None:
    """Freeze LXC and optionally lock GPUs to minimum clocks.
    
    Order: Freeze LXC -> sleep 500ms -> lock memory clocks -> lock graphics clocks
    
    If gpu_explicit is True, GPU operations are performed even if LXC is already frozen.
    """
    current = read_cgroup_state(lxc_id)
    lxc_already_frozen = current == 1

    if lxc_already_frozen:
        if gpu_explicit and gpus:
            # LXC already frozen but user explicitly requested GPU lock
            time.sleep(0.5)
            lock_gpu_clocks(gpus)
            gpu_str = ",".join(str(g) for g in gpus)
            print(f"WARN: LXC {lxc_id} is already frozen. Freezing GPU {gpu_str} anyway.")
            return
        else:
            sys.exit(f"ERR: LXC {lxc_id} is already frozen.")

    # Freeze the LXC first
    write_cgroup(lxc_id, "1")
    verify_state(lxc_id, 1, "freeze")

    # Sleep 500ms after freezing
    time.sleep(0.5)

    if gpus:
        # Lock GPU clocks after sleep
        lock_gpu_clocks(gpus)
        gpu_str = ",".join(str(g) for g in gpus)
        print(f"DONE: LXC {lxc_id} frozen. GPU {gpu_str} frozen.")
    else:
        print(f"DONE: LXC {lxc_id} frozen.")


def thaw(lxc_id: str, gpus: list[int] | None) -> None:
    """Thaw LXC and optionally reset GPU clocks.
    
    Order: Reset memory clocks -> reset graphics clocks -> sleep 500ms -> thaw LXC
    """
    current = read_cgroup_state(lxc_id)
    lxc_already_thawed = current == 0

    if gpus:
        # Reset GPU clocks first
        reset_gpu_clocks(gpus)
        gpu_str = ",".join(str(g) for g in gpus)

        if lxc_already_thawed:
            print(f"WARN: LXC {lxc_id} is already thawed. Thawing GPU {gpu_str} anyway.")
            return

        # Sleep 500ms after resetting clocks
        time.sleep(0.5)

        # Then thaw the LXC
        write_cgroup(lxc_id, "0")
        verify_state(lxc_id, 0, "thaw")
        print(f"DONE: LXC {lxc_id} thawed. GPU {gpu_str} thawed.")
    else:
        if lxc_already_thawed:
            sys.exit(f"ERROR: LXC {lxc_id} is already thawed.")

        write_cgroup(lxc_id, "0")
        verify_state(lxc_id, 0, "thaw")
        print(f"DONE: LXC {lxc_id} thawed.")


def main() -> None:
    all_actions = FREEZE_ALIASES + THAW_ALIASES

    parser = argparse.ArgumentParser(
        description="Freeze/thaw LXC containers with GPU power management.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
    %(prog)s f 148           Freeze LXC, auto-detect GPUs from config
    %(prog)s f 148 -g 0      Freeze LXC (or lock GPUs if already frozen)
    %(prog)s f 148 -g 0,2    Freeze LXC, lock GPUs 0 and 2
    %(prog)s f 148 -ng       Freeze LXC only (no GPU operations)
    %(prog)s t 148           Thaw LXC, auto-detect and reset GPUs
    %(prog)s t 148 -ng       Thaw LXC only (no GPU operations)
""",
    )
    parser.add_argument(
        "action",
        choices=all_actions,
        help="Action to perform (f=freeze, t/u=thaw)",
    )
    parser.add_argument(
        "lxc_id",
        help="LXC container ID",
    )
    parser.add_argument(
        "-g", "--gpu",
        default=None,
        metavar="INDEX",
        help="GPU index(es): specify explicitly (0 or 0,2,3). With freeze, performs GPU ops even if already frozen.",
    )
    parser.add_argument(
        "-ng", "--no-gpu",
        action="store_true",
        help="Disable GPU operations (no nvidia-smi calls)",
    )

    args = parser.parse_args()

    if not args.lxc_id.isdigit():
        sys.exit(f"ERR: LXC ID must be numeric, got '{args.lxc_id}' instead")

    cgroup_path = get_cgroup_path(args.lxc_id)
    if cgroup_path.exists():
        try:
            cgroup_path.read_text()
        except PermissionError:
            sys.exit("ERR: must run as root")

    # Track whether --gpu was explicitly provided
    gpu_explicit = args.gpu is not None

    # Determine GPU list: None if disabled, otherwise parse the argument
    if args.no_gpu:
        gpus = None
    elif args.gpu is not None:
        gpus = parse_gpu_arg(args.gpu, args.lxc_id)
    else:
        # Default: auto-detect
        gpus = parse_gpu_arg("auto", args.lxc_id)

    if args.action in FREEZE_ALIASES:
        freeze(args.lxc_id, gpus, gpu_explicit)
    else:
        thaw(args.lxc_id, gpus)

    sys.exit(0)


if __name__ == "__main__":
    main()
