"""The experimentation department: the two-arm test the plan already promised and the
ledger that decides what it found.

`src/strategist/plan.py` writes a hypothesis and a success_test into every one of the eight
weeks, and `src/metrics/adapt.py` can rank posts by the hypothesis they ran under. What was
missing is the middle: nothing recorded which arm a post belonged to, and nothing said out
loud whether the week's test had paid off. This package owns both halves, and it computes
them from the numbers she typed - it never invents a result to fill the page."""
