# What?
A simple Python script to freeze and thaw (pause and resume) an LXC (Linux Container) and its child processes. Additionally, any attached Nvidia GPUs are downclocked to a minimum-power state.

This script accomplishes both goals at once:

```bash
root@localhost:~# /root/sh/lxc-freeze-thaw.py f 148
DONE: LXC 148 frozen. GPU 0 frozen.
root@localhost:~# /root/sh/lxc-freeze-thaw.py t 148
DONE: LXC 148 thawed. GPU 0 thawed.
```

If an Nvidia GPU is not specified by the LXC config, it isn't frozen. If the LXC has no GPU attached, then no GPU is affected.

For detailed usage info, run `lxc-freeze-thaw.py --help`. Or just read the script, it's pretty short.

# Why?
Proxmox does not offer native integration (via the GUI, CLI or API) for freezing/thawing an LXC container, despite this being a standard feature of Linux cgroups v2, e.g. via the command: `echo 1 > /sys/fs/cgroup/lxc/148/cgroup.freeze`. Proxmox *does* support pausing/resuming QEMU VMs, so I felt that feature parity was lacking.

Now, even if Proxmox *did* support freezing cgroups/LXCs, that behavior still would not extend to any attached Nvidia GPUs - and that was the initial goal of this script.

Additionally, many long-running programs which leverage hardware acceleration do not offer true pause/resume features. You're often forced to choose between waiting for task completion, or abandoning progress since the last checkpoint. Linux commands respond gracefully to SIGTERM and SIGCONT, but hardware acceleration adds significant complexity. This script is my first attempt at extending pause/resume functionality to the GPU by throttling it to a minimum power or idle state.

So, problem solved! Necessity is the mother of invention, especially when your Homelab doubles as a space heater...

# How?
The script works by leveraging Linux cgroups v2 freeze functionality and Nvidia GPU power management. When freezing:

1. The LXC container is frozen using cgroups v2's `cgroup.freeze` interface
2. Any attached Nvidia GPUs are throttled into a minimum-power state using `nvidia-smi`
3. The script verifies both operations completed successfully

And when thawing:
1. The LXC container is thawed
2. Any attached Nvidia GPUs are returned to full power state
3. The script verifies both operations completed successfully

The script includes error handling for cases where:
- The LXC container doesn't exist
- The cgroup freeze file doesn't exist
- Nvidia GPUs aren't detected
- Any operation fails mid-execution

# Caveats
There are some sharp edges to be wary of:
- If an LXC is frozen, any Proxmox backup jobs will stall until the LXC is thawed.
- If the GPU is shared by multiple LXC's, but only one LXC is frozen, the unfrozen LXC's will still have access to the GPU, despite it being in an extremely power-limited state.
- When invoked in `-ng` mode, bypassing GPU operations, it's still possible to freeze an LXC with an attached GPU. Doing so will "orphan" the GPU, and it will continue calculating until ready for more instructions. Thawing the LXC after that can lead to unexpected behavior and process crashes.
- Not tested and not production-ready! Don't blame me if this script eats your homework or crashes your system. Written for personal use only.
- This script is hacky on multiple levels. If you can't read it, you shouldn't be comfortable using it.
- The script includes brief sleep periods before and after performing GPU operations. This is for safety, and not out of necessity, since we always fear the unknown. :)
- I don't own an AMD card, sorry.

# License
MIT license. No rights reserved. Go crazy, steal it, I don't care.
