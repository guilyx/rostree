# Demo media

| File | What it is |
|------|-----------|
| `rostree-demo.gif` | 28 s loop used in the project README |
| `rostree-demo.mp4` | 68 s promo reel (full cut, with the before/after comparison) |
| `tui-packages.png`, `tui-tree.png`, `tui-dependents.png` | TUI screenshots |

## How they were made, and what is real in them

- **The terminal output is real.** Every command shown was executed and its output
  captured with ANSI colour intact; the reel only animates the reveal. The timings
  on the badges are wall-clock times of those runs, including interpreter startup.
- **The "before" numbers are real too.** They come from running the same commands
  against rostree 0.2.2, on the same machine and the same workspace. At unlimited
  depth 0.2.2 was still running after two minutes, which is what the reel shows.
- **The TUI screenshots are real.** They are captured from the running application
  through Textual's own screenshot support, not mocked up.
- **The workspace is synthetic.** It is generated: real ROS 2 and Nav2 package
  *names*, arranged in the layers they actually occupy (rcutils at the bottom,
  nav2_bringup at the top), with generated dependency edges. It is a workspace of
  realistic shape and size — 135 installed packages plus a 24-package source
  overlay — not a copy of the real navigation2 dependency graph. Do not read the
  edges in the demo as upstream fact.

The generator, capture and render scripts are not checked in; they are throwaway
tooling. To reproduce the measurements on your own workspace:

```bash
time rostree tree <your_package> -r
rostree tree <your_package> -r --full --max-nodes 200000   # the old behaviour
```
