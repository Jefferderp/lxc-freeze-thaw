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
Proxmox does not offer native integration (via the GUI, CLI or API) for freezing/thawing an LXC container, despite this being a standard feature of Linux cgroup v2, e.g. via `echo 0 > /sys/fs/cgroup/lxc/148/cgroup.freeze`

Even if it did support freezing, that behavior would not extend to any attached Nvidia GPUs.

Problem solved! Necessity is the mother of invention. Especially when your Homelab doubles as a space heater...

# How?
The script works by leveraging Linux cgroup v2 freeze functionality and Nvidia GPU power management. When freezing:

1. The LXC container is frozen using cgroup v2's `cgroup.freeze` interface
2. Any attached Nvidia GPUs are put into a low-power state using `nvidia-smi`
3. The script verifies both operations completed successfully

When thawing:

1. The LXC container is thawed
2. Any attached Nvidia GPUs are returned to full power state
3. The script verifies both operations completed successfully

The script includes error handling for cases where:
- The LXC container doesn't exist
- The cgroup freeze file doesn't exist
- Nvidia GPUs aren't properly detected
- Any operation fails mid-execution

# Caveats
- If the GPU is shared by multiple LXC's, but only one LXC is frozen, the unfrozen LXC's will still have access to the GPU, despite it being in an extremely power-limited state.
- Not tested and not production-ready! Don't blame me if this script eats your homework or crashes your system. Written for personal use only.
- This script is hacky on multiple levels. If you can't read it, you shouldn't be comfortable using it.
- I don't own an AMD card, sorry.

# License
MIT license. No rights reserved. Go crazy, steal it, I don't care.
