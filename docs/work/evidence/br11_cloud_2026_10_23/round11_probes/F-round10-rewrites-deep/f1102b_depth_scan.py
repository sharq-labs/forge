"""R11-F f1102b: the depth window in which a spend's experiment is owner-readable but the reader's read-back escapes
(seq order of f1102: verification on the spend, restore, re-dispatch)."""
import sys
sys.argv = [sys.argv[0]]
import importlib.util
spec = importlib.util.spec_from_file_location("f1102", __file__.replace("f1102b_depth_scan.py", "f1102_readback_escape_redispatch.py"))
src = open(spec.origin).read().split("for order in")[0]
ns = {"__file__": spec.origin, "__name__": "f1102"}
exec(compile(src, spec.origin, "exec"), ns)
for depth in (300, 400, 450, 480, 500, 700, 900, 1000, 1500, 2500, 5000):
    try:
        print(depth, ns["run"]("seq", depth))
    except Exception as exc:  # noqa: BLE001
        print(depth, "probe raised", type(exc).__name__, str(exc)[:100])
