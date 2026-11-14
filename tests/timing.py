"""One timing helper for the two tests that hold the edit engines to a speed budget.

A single sample of a wall clock on this laptop has been measured swinging 3x between
adjacent runs of the identical Pillow pass, so a budget built from one sample prices the
moment rather than the code - which shows up as an engine test that passes alone and fails
in the middle of a busy suite. Medians on both sides of the comparison keep the teeth (a
Python pixel loop costs a hundred passes, which no sampling noise reaches) and stop the
flake.
"""

import time
from statistics import median


def median_of(work, runs=3):
    """The middle of `runs` timings of the same call, plus the last result so the caller
    does not have to run it again to get the picture."""
    took, value = [], None
    for _ in range(runs):
        started = time.time()
        value = work()
        took.append(time.time() - started)
    return max(median(took), 0.01), value
