"""Numerics written for this round, used only by the reference branch.

Nothing here imports engcore, and nothing here imports the adapters. The
separation matters for a specific reason: the Core reaches LAPACK through
``scipy.linalg.solve`` for DC, ``scipy.integrate.solve_ivp`` and
``scipy.optimize.brentq`` for the reactor, and ``scipy.sparse.linalg`` for the
slab. A reference that called any of those would be sharing a numerical kernel
with the thing it is checking. ``numpy.linalg.solve`` is excluded for the same
reason: it dispatches to the same LAPACK driver scipy does.
"""
