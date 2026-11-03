# Examples

Small, complete programs built on `rostree.api`. Each one runs against whatever
ROS 2 environment is sourced, and each is exercised by `tests/test_examples.py`
against a generated workspace, so they keep working as the library changes.

| Script | What it shows |
|---|---|
| [`forbidden_dependencies.py`](forbidden_dependencies.py) | An architecture rule for CI, with the chain that breaks it |
| [`ripple_report.py`](ripple_report.py) | Which packages a change would ripple furthest from |
| [`drift_gate.py`](drift_gate.py) | Fail a PR whose dependency set changed without saying so |
| [`export_edges.py`](export_edges.py) | The graph in a format rostree does not ship (CSV) |

They are explained in [Build on rostree](https://guilyx.github.io/rostree/extending/).
