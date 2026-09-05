"""Thermal models and realizations that live beside the frozen ``thermal`` tree.

``engcore.domains.thermal`` is byte-pinned by the T1/T2/T3, MODEL0-R and
DATA-BOUNDARY0 experiments: nothing may be added to or edited in that tree
without a formal re-freeze. Thermal work that post-dates those freezes is
kept here instead.

- ``lumped``                first-order lumped-capacity exchange with ambient
- ``conduction1d_schemes``  explicit/implicit scheme realizations of the
                            frozen 1-D conduction model
- ``conduction1d_bulk``     bulk field capture for that model through the
                            data boundary

At the next planned re-freeze of the thermal domain these modules fold into
``engcore.domains.thermal``.
"""
