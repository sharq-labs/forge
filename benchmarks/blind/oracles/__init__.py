"""Independent oracles. A second implementation, never the runtime's.

Each module here re-derives the quantities one domain's validity conditions are
stated over, from the sources named in its own docstring, on plain floats in
SI. They share no unit library, no quantity type and no solver with Forge.

What they DO share, on purpose, is the contract: what each condition means and
which state coordinate it is read at. A second implementer given a spec
implements the spec. An oracle that guessed would test whether two authors
guessed alike rather than whether the arithmetic is right, and the arithmetic
is where a defect lives.
"""
