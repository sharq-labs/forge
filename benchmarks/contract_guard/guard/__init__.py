"""Executable contract guards.

The Contract Integrity round proved by hand that 16 shipped records agree with
their runtimes. It left one executable guard behind, on one model. A hand proof
protects nothing tomorrow.

This package turns that proof into machinery that runs with the suite. Two
mechanisms carry almost all of it, and both are generic rather than per-model:

``enforcement`` -- every condition publishes a STRUCTURED bound (a minimum, a
maximum and their inclusivity). Feed the model's own ``assess_validity`` a
synthetic value at, inside and outside that bound and check it classifies the
value the way the record says. This needs no domain nominal and works for every
condition in every model.

``prose`` -- every condition also publishes PROSE about the same bound. The
prose and the structured bound must say the same thing. A record whose words
drift from its own numbers is the SC5 class, and it is what this half catches.
"""
