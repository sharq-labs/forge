"""Independent oracles.

Nothing in this package imports ``engcore``. Every routine here is written
from the physics, in this audit's own algebra, so that a disagreement with the
production code is evidence rather than a tautology. Where an equation is
quoted it is quoted from the literature or derived in the docstring, never
copied from the implementation under test.

The one thing these oracles share with production is the *problem statement* —
the numbers a caller declares. That is unavoidable and is not shared
derivation.
"""
