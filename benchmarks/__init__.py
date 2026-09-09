"""Package marker so `benchmarks.blind` is importable as a package.

Nothing else lives here. `benchmarks/hard` is deliberately NOT a package: its
scorer is run as a script and resolves its neighbours through `sys.path`, and
turning it into one would change how every existing invocation imports it.
"""
