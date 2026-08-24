# Demo media

| File | What it is |
|------|-----------|
| `rostree-demo.gif` | 24 s loop used in the project README |
| `rostree-demo.mp4` | 82 s promo reel — the full cut |
| `rostree-1.0.gif` | 22 s loop for the 1.0 release announcement |
| `rostree-1.0.mp4` | 71 s 1.0 launch reel |
| `graph-html.png`, `graph-html-light.png` | The interactive HTML graph, both themes |
| `tui-packages.png`, `tui-tree.png`, `tui-dependents.png` | TUI screens |

`rostree-demo.*` names no version, so it stays correct as the README asset release
after release. `rostree-1.0.*` is the launch cut and is meant to date: it opens on
1.0 and closes on what 1.0 does and does not promise.

## What is real in them, and what is not

**The terminal is a real session, recorded at its real speed.** The reel is not a
reconstruction. A `bash` session runs inside a pty; commands are typed into it a
character at a time; every byte the session writes back is recorded with a
timestamp. Playback feeds that byte stream to a VT emulator and photographs the
screen at 30 fps, so the typing cadence, the pause while the package index is
built, and the scroll are the ones that happened. Long dead air is capped at
0.9 s — the only liberty taken with the timeline, and it can only make the tool
look *slower* relative to its own output, never faster.

**The TUI screens are real.** The application runs in the same pty at 110×25 and
receives actual key presses — the filter is typed, the tree is walked with the
arrow keys, `v` and `?` are pressed. Its worker threads do their own work.

**The graph segment is a real screen recording.** It is the `graph.html` produced
by `rostree graph -f html`, opened from a `file://` URL in Chromium and driven with
real pointer and keyboard input. The mouse pointer you see is drawn by a script
injected into the page and moved by the page's own `mousemove` events, because the
recorder does not capture a system cursor; it tracks the input that actually drove
the page.

**The before/after numbers are measured, not remembered.** `rostree` 0.2.2 was
installed from PyPI into a separate virtualenv and run against the same workspace
on the same machine, alternating with the current build. Resolving
`my_robot_bringup` with `-r`:

| depth | 0.2.2 | now |
|-------|-------|-----|
| 5 | 1,901 lines / 0.30 s | 278 lines / 0.15 s |
| 6 | 6,353 lines / 0.86 s | 255 lines / 0.14 s |
| 7 | 16,941 lines / 2.01 s | 254 lines / 0.14 s |
| no depth limit (the default) | 60,981 lines / 7.11 s | 253 lines / 0.15 s |

Times are wall clock for the whole process, interpreter startup included, from a
single run each — they wobble by a few tens of a second between runs. The line
counts are deterministic. These are not the same figures recorded for the 1.0 reel:
the workspace gained two dependencies on `my_robot_navigation` so that the `diff`
segment would have real drift to report, which moves every number a little. Note
also that 0.2.2 *does* finish at unlimited depth on this workspace; on a deeper one
it does not, but that is not what was measured here.

One number on screen deserves a note, because it does not match the caption.
`rostree tree` reports `406 line(s)` in its summary, and the reel says the tree
prints 253. Both are right: the summary counts **nodes**, and sibling
back-references are then grouped onto one line each when printed, so 406 nodes come
out as 253 lines of terminal. The reel compares printed lines to printed lines.

**The workspace is synthetic.** It is generated: real ROS 2 and Nav2 package
*names*, arranged in the layers they really occupy (`rcutils` at the bottom,
`nav2_bringup` near the top), with **generated** dependency edges — plus a
24-package `my_robot_*` source overlay standing in for your own workspace. 122
installed packages under `/opt/ros/jazzy` and 24 source packages under
`~/robot_ws/src`, so a realistic shape, size and set of paths, but not a copy of
the real navigation2 graph.

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
