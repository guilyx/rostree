# Demo media

| File | What it is |
|------|-----------|
| `rostree-demo.gif` | 27 s loop used in the project README |
| `rostree-demo.mp4` | 79 s promo reel — the full cut |

Neither names a version number, so neither goes stale on release day.

| `graph-html.png`, `graph-html-light.png` | The interactive HTML graph, both themes |
| `tui-packages.png`, `tui-tree.png`, `tui-dependents.png` | TUI screens |

## What is real in them, and what is not

**The terminal output is real.** Every command in the reel was executed against the
workspace described below and its ANSI output captured. The reel re-renders that
output on a monospace grid and animates the reveal; nothing is retyped, and no
output was edited. The only thing removed is the progress spinner, which a live
terminal draws and then erases.

**The TUI screens are real.** The application was run in a pty at 104×30, driven
with actual keystrokes, and its screen buffer captured — not mocked up.

**The graph segment is a real screen recording.** It is the `graph.html` produced
by `rostree graph -f html`, opened from a `file://` URL in Chromium and driven
with real pointer and keyboard input. The hover highlighting, the re-centring, the
search and the pinned paths are the page doing its job.

**The before/after numbers are measured, not remembered.** `rostree` 0.2.2 was
installed from PyPI into a separate virtualenv and run against the same workspace
on the same machine, alternating with the current build:

| depth | 0.2.2 | now |
|-------|-------|-----|
| 5 | 1,876 lines / 0.43 s | 276 lines / 0.20 s |
| 6 | 6,258 lines / 1.18 s | 253 lines / 0.18 s |
| 7 | 16,623 lines / 3.04 s | 252 lines / 0.19 s |
| no depth limit (the default) | 58,002 lines / 10.29 s | 251 lines / 0.21 s |

Times are wall clock for the whole process, interpreter startup included, from a
single run each — they wobble by a few tens of a second between runs. The line
counts are deterministic. Note that 0.2.2 *does* finish at unlimited depth on this
workspace; on a deeper one it does not, but that is not what was measured here.

**The workspace is synthetic.** It is generated: real ROS 2 and Nav2 package
*names*, arranged in the layers they really occupy (`rcutils` at the bottom,
`nav2_bringup` near the top), with **generated** dependency edges — plus a
24-package `my_robot_*` source overlay standing in for your own workspace. 122
installed packages and 24 source packages, so a realistic shape and size, but not
a copy of the real navigation2 graph.

**Do not read the edges in the demo as upstream fact.** `my_robot_bringup → rclcpp`
in the reel says something about rostree, nothing about Nav2.

## Reproducing the measurement

The generator and capture scripts are not checked in — they are single-use tooling
that would rot against the next CLI change. To take the same measurement on a
workspace you actually care about:

```bash
python -m venv /tmp/old && /tmp/old/bin/pip install 'rostree==0.2.2'

time /tmp/old/bin/rostree tree <your_package> -r     # before
time rostree tree <your_package> -r                  # after
```

Pipe both through `wc -l` for the line counts.
