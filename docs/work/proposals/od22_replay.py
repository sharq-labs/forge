"""OD-22: exact-rational replay of the window-control sequence (pure stdlib, no engcore).

Re-implements, from a reading of runtime.py (main loop nominal/forced target, _controlled_window,
_next_window_width) and the test fixture (tests/test_multiphysics_window_control.py:_explicit_runtime),
the window boundaries for horizon [0, 2], coupling window 1/2, sink unstable above 1/4 s
(converged iff width <= 0.25 + 1e-12), reduction 1/2, max 4 subdivisions, minimum window 1/10.
"""
from fractions import Fraction as F


def replay(growth=None, end=F(2), nominal_width=F(1, 2), max_stable=0.25, reduction=F(1, 2),
           max_subdivisions=4, minimum=F(1, 10)):
    current, width, windows, subdivided_total = F(0), nominal_width, [], 0
    while current < end:
        nominal = current + width
        forced = end  # no events, no input changes
        target = forced if forced <= nominal else nominal
        attempt_end, subdivisions = target, 0
        while True:
            span = attempt_end - current
            if float(span) <= max_stable + 1e-12:
                break
            next_width = span * reduction
            if subdivisions >= max_subdivisions or next_width < minimum:
                raise RuntimeError("exhausted")
            attempt_end = current + next_width
            subdivisions += 1
        subdivided_total += subdivisions
        windows.append((current, attempt_end, subdivisions))
        accepted = attempt_end - current
        if growth is not None:
            width = accepted if subdivisions else min(nominal_width, width * F(growth))
        current = attempt_end
    return subdivided_total, windows


for label, growth in (("no memory", None), ("growth 2", 2)):
    total, windows = replay(growth)
    print(f"{label}: {total} subdivisions over {len(windows)} accepted windows")
    for start, stop, k in windows:
        print(f"  [{start}, {stop}]  subdivisions={k}")
