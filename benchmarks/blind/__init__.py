"""The blind scientific challenge: truth first, freeze second, Forge third.

See `README.md` in this directory for what the round is and how to reproduce
it, and `BLIND_CHALLENGE_SPEC.json` for the contract it was run under.

Nothing in this package may import `engcore`. That is enforced, not asked:
`tests/test_blind_challenge_guards.py` walks the import graph of every module
here and fails if an edge into the runtime appears.
"""
