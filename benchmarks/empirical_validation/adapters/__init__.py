"""The two branches of the comparison, kept apart on purpose.

``adapter_a`` turns a raw fixture into engcore declarations and runs the Core.
``adapter_b`` turns the same raw fixture into plain SI numbers for the reference
branch.

They do not import each other. ``adapter_b`` does not import engcore. Neither
imports a shared problem-construction helper, because there is none: every
conversion factor and every derived quantity is written out twice, once in each
file, and the round's whole value rests on that duplication. A shared helper
would make a unit fault invisible to both sides at once, which is precisely the
blindness this round exists to remove.
"""
